import base64
import json
import re

from fake_github import comment, pull_request, thread
from review_case import ReviewCase

MARKER = '<!-- pack-review -->'
HEAD = 'h' * 40
MUTATIONS = ['AddReview', 'AddReply', 'Resolve', 'AddComment', 'UpdateComment']


def finding(kind='deviates', inline=True, headline='A game number in sim code'):
    return {'kind': kind, 'inline': inline, 'headline': headline, 'rules': [], 'spots': [], 'deliberate': [],
            'exemplars': [], 'take': 'Move it to content.'}


def own(body, id='IC_1'):
    """A comment pack-review posted earlier."""
    return comment(f'🤖 {body}\n\n{MARKER}', login='github-actions', association='NONE', mine=True, id=id)


def block(body):
    """The findings in a summary's hidden block."""
    encoded = re.search(r'<!-- pack-review:findings\n([A-Za-z0-9+/=\n]+)\n-->', body).group(1)
    return json.loads(base64.b64decode(encoded))


class PostTests(ReviewCase):
    """What lands on the PR from a review: the agent's thread actions, carried out only on pack-review's own
    threads, and one summary kept current."""

    def setUp(self):
        super().setUp()
        self.github.responses.update({name: {'data': {}} for name in MUTATIONS})
        self.pr(pull_request())

    def pr(self, response):
        self.github.responses['PullRequest'] = response

    def post(self, findings=(), threads=(), head=HEAD):
        (self.root / 'findings.json').write_text(json.dumps(
            {'base': 'b' * 40, 'head': head, 'findings': list(findings), 'threads': list(threads)}))
        return self.script('post', '--pr', 7, '--findings', 'findings.json')

    def sent(self, operation):
        return [request['variables'] for request in self.github.requests if request['operationName'] == operation]

    def summary(self):
        [sent] = self.sent('AddComment') or self.sent('UpdateComment')
        return sent['input']['body']

    def test_opens_new_threads_as_one_review_of_the_head_commit(self):
        result = self.post([finding()], [
            {'action': 'new', 'path': 'src/sim/slow.ts', 'line': 3, 'body': 'Deviates from a rule.'},
            {'action': 'new', 'path': 'src/sim/fast.ts', 'line': 9, 'body': 'Conflicting rules.'}])

        self.assertEqual(result.returncode, 0, result.stderr)
        [review] = self.sent('AddReview')
        self.assertEqual(review['input'], {
            'pullRequestId': 'PR_1', 'commitOID': HEAD, 'event': 'COMMENT',
            'body': f'🤖 pack-review opened 2 threads on `hhhhhhh`.\n\n{MARKER}', 'threads': [
                {'path': 'src/sim/slow.ts', 'line': 3, 'side': 'RIGHT', 'body': f'🤖 Deviates from a rule.\n\n{MARKER}'},
                {'path': 'src/sim/fast.ts', 'line': 9, 'side': 'RIGHT', 'body': f'🤖 Conflicting rules.\n\n{MARKER}'},
            ]})

    def test_replies_in_its_own_threads(self):
        self.pr(pull_request(threads=[thread([own('Deviates.'), comment('It is deliberate.', login='bob')])]))

        result = self.post([finding()], [{'action': 'reply', 'thread': 'PRRT_1', 'body': 'Take changed.'}])

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.sent('AddReply'), [{'input': {'pullRequestReviewThreadId': 'PRRT_1',
                                                            'body': f'🤖 Take changed.\n\n{MARKER}'}}])
        self.assertEqual(self.sent('AddReview'), [])

    def test_resolves_its_own_thread_after_a_closing_note(self):
        self.pr(pull_request(threads=[thread([own('Deviates.')])]))

        result = self.post([], [{'action': 'resolve', 'thread': 'PRRT_1', 'body': 'Moved to content.'}])

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.sent('AddReply'), [{'input': {'pullRequestReviewThreadId': 'PRRT_1',
                                                            'body': f'🤖 Moved to content.\n\n{MARKER}'}}])
        self.assertEqual(self.sent('Resolve'), [{'input': {'threadId': 'PRRT_1'}}])
        operations = self.github.operations()
        self.assertLess(operations.index('AddReply'), operations.index('Resolve'))

    def test_refuses_to_touch_a_thread_it_didnt_start_and_writes_nothing(self):
        self.pr(pull_request(threads=[
            thread([comment('Why?', login='bob'), own('Answered.')], id='PRRT_bob'),
            thread([comment('Lint: unused import.', login='github-actions', association='NONE', mine=True)],
                   id='PRRT_lint'),
            thread([comment(f'Pretend.\n\n{MARKER}', login='bob')], id='PRRT_forged')]))

        for action in ('reply', 'resolve'):
            for id in ('PRRT_bob', 'PRRT_lint', 'PRRT_forged', 'PRRT_unknown'):
                with self.subTest(action=action, thread=id):
                    result = self.post([finding()], [
                        {'action': 'new', 'path': 'src/sim/slow.ts', 'line': 3, 'body': 'Deviates.'},
                        {'action': action, 'thread': id, 'body': 'Done.'}])

                    self.assertEqual(result.returncode, 1)
                    self.assertIn(f'{id} is not a thread pack-review started', result.stderr)
                    self.assertEqual(set(self.github.operations()), {'PullRequest'})
                    self.github.requests.clear()

    def test_refuses_an_action_missing_what_it_needs(self):
        for action, missing in [({'action': 'new', 'line': 3, 'body': 'x'}, 'path'),
                                ({'action': 'new', 'path': 'a.ts', 'body': 'x'}, 'line'),
                                ({'action': 'reply', 'body': 'x'}, 'thread'),
                                ({'action': 'resolve', 'body': 'x'}, 'thread')]:
            with self.subTest(action=action):
                result = self.post([], [action])

                self.assertEqual(result.returncode, 1)
                self.assertIn(f'a {action["action"]} action needs a {missing}', result.stderr)
                self.assertEqual(set(self.github.operations()), {'PullRequest'})
                self.github.requests.clear()

    def test_writes_nothing_else_when_github_refuses_the_new_threads(self):
        self.pr(pull_request(threads=[thread([own('Deviates.')])]))
        self.github.responses['AddReview'] = {'data': None, 'errors': [{'message': 'line must be part of the diff'}]}

        result = self.post([finding()], [{'action': 'new', 'path': 'src/a.ts', 'line': 99, 'body': 'x'},
                                         {'action': 'reply', 'thread': 'PRRT_1', 'body': 'y'}])

        self.assertEqual(result.returncode, 1)
        self.assertIn('line must be part of the diff', result.stderr)
        self.assertEqual(self.github.operations(), ['PullRequest', 'AddReview'])

    def test_posts_a_summary_counting_the_findings_and_holding_them_all(self):
        findings = [finding(), finding(), finding('conflicting'), finding('uncovered'),
                    finding('uncovered', inline=False), finding('uncovered', inline=False)]

        result = self.post(findings)

        self.assertEqual(result.returncode, 0, result.stderr)
        [sent] = self.sent('AddComment')
        self.assertEqual(sent['input']['subjectId'], 'PR_1')
        body = self.summary()
        self.assertTrue(body.startswith('🤖 '))
        self.assertTrue(body.endswith(MARKER))
        self.assertIn('`hhhhhhh`', body)
        self.assertIn('Commented on the diff: 2 deviations, 1 conflict, 1 uncovered choice.', body)
        self.assertIn("For the author's local review only: 2 uncovered choices.", body)
        self.assertIn('/pack-review 7', body)
        self.assertEqual(block(body), {'base': 'b' * 40, 'head': HEAD, 'findings': findings})

    def test_says_when_it_found_nothing(self):
        self.post([])

        body = self.summary()
        self.assertIn('found nothing', body)
        self.assertNotIn('Commented on the diff', body)
        self.assertEqual(block(body)['findings'], [])

    def test_updates_its_summary_rather_than_adding_another(self):
        self.pr(pull_request(comments=[comment('Thanks!', login='bob', id='IC_bob'), own('Old summary.', id='IC_9'),
                                       comment('Coverage: 80%.', login='github-actions', association='NONE',
                                               mine=True, id='IC_ci')]))

        result = self.post([finding()])

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.sent('AddComment'), [])
        [sent] = self.sent('UpdateComment')
        self.assertEqual(sent['input']['id'], 'IC_9')

    def test_stops_when_it_finds_two_summaries_of_its_own(self):
        self.pr(pull_request(comments=[own('Summary.', id='IC_1'), own('Summary.', id='IC_2')]))

        result = self.post([finding()])

        self.assertEqual(result.returncode, 1)
        self.assertIn('IC_1, IC_2', result.stderr)
        self.assertEqual(set(self.github.operations()), {'PullRequest'})

    def test_posts_the_summary_last(self):
        self.pr(pull_request(threads=[thread([own('Deviates.')])]))

        self.post([finding()], [{'action': 'new', 'path': 'src/a.ts', 'line': 3, 'body': 'x'},
                                {'action': 'reply', 'thread': 'PRRT_1', 'body': 'y'}])

        self.assertEqual(self.github.operations(), ['PullRequest', 'AddReview', 'AddReply', 'AddComment'])

    def test_posts_nothing_when_the_pr_moved_on_since_the_review(self):
        result = self.post([finding()], [{'action': 'new', 'path': 'src/a.ts', 'line': 3, 'body': 'x'}],
                           head='o' * 40)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f'moved on to {HEAD}', result.stdout)
        self.assertEqual(self.github.operations(), ['PullRequest'])

    def test_stops_before_writing_when_the_summary_wont_fit_in_a_comment(self):
        result = self.post([finding(headline='x' * 60000)])

        self.assertEqual(result.returncode, 1)
        self.assertIn('65536', result.stderr)
        self.assertEqual(self.github.operations(), ['PullRequest'])
