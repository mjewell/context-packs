import json

from fake_github import connection, ok, pull_request, role
from review_case import HEAD, MARKER, ReviewCase
from test_review_pairing import F1, F3, finding
from test_review_trust import ours

BASE = 'b' * 40


def thread(id, resolved=False, replies=()):
    """A pack-review thread as GitHub's GraphQL API returns it: the comment pack-review opened it with, then replies."""
    return {'id': id, 'path': 'src/sim.ts', 'line': 42, 'isResolved': resolved,
            'comments': connection([ours(id=f'{id}_c'), *replies])}


class PostCase(ReviewCase):
    """The post job: the find job's report, the threads job's pairs and commentary, and the PR on the fake GitHub."""

    def setUp(self):
        super().setUp()
        self.github.responses.update({
            'PullRequest': pull_request(),
            'Threads': ok({'repository': {'pullRequest': {'reviewThreads': connection([])}}}),
            'AddReview': ok({'addPullRequestReview': {'pullRequestReview': {'id': 'PRR_1'}}}),
            'AddReply': ok({'addPullRequestReviewThreadReply': {'comment': {'id': 'RC_9'}}}),
            'AddComment': ok({}),
        })
        self.github.rest['/repos/o/r/collaborators/alice/permission'] = role('write')

    def threads(self, *threads):
        self.github.responses['Threads'] = ok({'repository': {'pullRequest': {
            'reviewThreads': connection(list(threads))}}})

    def post(self, findings, anchors, pairs=(), commentary=()):
        (self.root / 'report.json').write_text(json.dumps({
            'base': BASE, 'base_ref': 'main', 'head': HEAD, 'findings': findings, 'anchors': anchors}))
        (self.root / 'paired.json').write_text(json.dumps({'pairs': list(pairs), 'commentary': list(commentary)}))
        return self.script('post', '--pr', 7, '--report', 'report.json', '--paired', 'paired.json')

    def review(self):
        """What the post wrote in threads: the review that opened the new threads, or None when there were none, and
        the replies by thread. No review is ever left pending: the new threads are submitted as they're created, and
        each reply is posted on its own."""
        self.assertEqual(self.sent('SubmitReview'), [])
        added = [sent['input'] for sent in self.sent('AddReview')]
        self.assertLessEqual(len(added), 1)
        for review in added:
            self.assertEqual(review['event'], 'COMMENT')
        replies = {sent['input']['pullRequestReviewThreadId']: sent['input'] for sent in self.sent('AddReply')}
        for reply in replies.values():
            self.assertNotIn('pullRequestReviewId', reply)
        return (added[0] if added else None), replies


class NewThreadTests(PostCase):
    """A finding no thread was opened for gets a thread of its own, on the spot report.py anchored it to."""

    def test_opens_a_thread_on_each_new_findings_anchor(self):
        result = self.post([F1, F3], [{'path': 'src/sim.ts', 'line': 42}, {'path': 'src/rng.ts', 'line': 17}])

        self.assertEqual(result.returncode, 0, result.stderr)
        added, replies = self.review()
        self.assertEqual(added['pullRequestId'], 'PR_1')
        self.assertEqual(added['commitOID'], HEAD)
        self.assertEqual([(t['path'], t['line'], t['side']) for t in added['threads']],
                         [('src/sim.ts', 42, 'RIGHT'), ('src/rng.ts', 17, 'RIGHT')])
        self.assertEqual(replies, {})

    def test_opens_it_with_the_finding_written_for_people_and_for_later_runs_to_pair(self):
        found = {**F1, 'rules': [{'file': 'AGENTS.md', 'quote': 'Game numbers live in content.', 'routed': True}]}

        self.post([found], [{'path': 'src/sim.ts', 'line': 42}])

        added, _ = self.review()
        self.assertEqual(added['threads'][0]['body'],
                         '🤖 `deviation` `hhhhhhh` **A game number in sim code**\n\n'
                         'From `AGENTS.md`:\n\n> Game numbers live in content.\n\n'
                         'Move it to content.\n\n' + MARKER)

    def test_keeps_the_findings_text_from_notifying_anyone_or_hiding_text(self):
        found = {**F1, 'headline': 'Ask @alice <!-- or not -->', 'take': 'See <b>this</b>.'}

        self.post([found], [{'path': 'src/sim.ts', 'line': 42}])

        added, _ = self.review()
        body = added['threads'][0]['body']
        self.assertIn('**Ask @\u2060alice &lt;!-- or not -->**', body)
        self.assertIn('See &lt;b>this&lt;/b>.', body)
        self.assertNotIn('```json', body)

    def test_opens_no_thread_for_a_finding_the_diff_doesnt_show(self):
        result = self.post([F1], [None])

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.github.writes(), ['AddComment'])


class PairedTests(PostCase):
    """A finding that continues a thread is answered in it only when there's something to say."""

    def test_stays_quiet_on_an_open_thread_with_nothing_to_add(self):
        self.threads(thread('T_1'))

        result = self.post([F1], [{'path': 'src/sim.ts', 'line': 42}], pairs=[{'finding': 0, 'thread': 'T_1'}])

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.github.writes(), ['AddComment'])
        self.assertIn('opened 0 threads, replied in 0', result.stdout)

    def test_tells_a_resolved_thread_its_finding_is_still_found(self):
        self.threads(thread('T_1', resolved=True))

        self.post([F1], [None], pairs=[{'finding': 0, 'thread': 'T_1'}])

        added, replies = self.review()
        self.assertIsNone(added)
        body = replies['T_1']['body']
        self.assertEqual(body, f'🤖 `still found` `hhhhhhh`\n\n{MARKER}')
        self.assertTrue(body.endswith(MARKER))

    def test_says_still_found_once_while_the_thread_stays_resolved(self):
        self.threads(thread('T_1', resolved=True, replies=[ours('🤖 still found 1234567', id='RC_8')]))

        result = self.post([F1], [None], pairs=[{'finding': 0, 'thread': 'T_1'}])

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.github.writes(), ['AddComment'])

    def test_names_the_thread_when_github_refuses_a_reply(self):
        self.github.responses['AddReply'] = (200, {'data': None, 'errors': [{'message': 'Thread is locked'}]})
        self.threads(thread('T_1', resolved=True))

        result = self.post([F1], [None], pairs=[{'finding': 0, 'thread': 'T_1'}])

        self.assertEqual(result.returncode, 1)
        self.assertIn('T_1', result.stderr)
        self.assertIn('Thread is locked', result.stderr)

    def test_stops_on_a_pair_with_a_thread_that_isnt_pack_reviews_on_this_pr(self):
        self.threads(thread('T_1'))

        result = self.post([F1], [None], pairs=[{'finding': 0, 'thread': 'T_9'}])

        self.assertEqual(result.returncode, 1)
        self.assertIn('T_9', result.stderr)
        self.assertEqual(self.github.writes(), [])


class StaleTests(PostCase):
    def test_posts_nothing_when_the_pr_moved_on_or_to_another_base(self):
        for answer, says in ((pull_request(head='o' * 40), 'moved on'), (pull_request(base_ref='release'), 'moved from main')):
            with self.subTest(says=says):
                self.github.responses['PullRequest'] = answer

                result = self.post([F1], [{'path': 'src/sim.ts', 'line': 42}])

                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(says, result.stdout)
                self.assertEqual(self.github.writes(), [])


class BeforeWritingTests(PostCase):
    """Every check that can fail runs before the first write, so a run that stops leaves the PR as it was."""

    def test_writes_nothing_when_the_summary_wont_fit_though_each_thread_would(self):
        findings = [{**F1, 'headline': 'x' * 33000}, {**F3, 'headline': 'y' * 33000}]

        result = self.post(findings, [{'path': 'src/sim.ts', 'line': 42}, {'path': 'src/rng.ts', 'line': 17}])

        self.assertEqual(result.returncode, 1)
        self.assertIn('65536', result.stderr)
        self.assertEqual(self.github.writes(), [])


class CommentaryTests(PostCase):
    """Commentary is posted in its finding's thread, open or resolved, as a quote that can't notify anyone or hide
    text."""

    def reply(self, text, resolved=False):
        self.threads(thread('T_1', resolved=resolved))
        result = self.post([F1], [None], pairs=[{'finding': 0, 'thread': 'T_1'}],
                           commentary=[{'finding': 0, 'text': text}])
        self.assertEqual(result.returncode, 0, result.stderr)
        _, replies = self.review()
        return replies['T_1']['body']

    def test_replies_with_the_commentary_on_an_open_thread(self):
        self.assertEqual(self.reply('Alice says this is deliberate, per the balance spec.'),
                         f'🤖 `hhhhhhh`\n\n> Alice says this is deliberate, per the balance spec.\n\n{MARKER}')

    def test_keeps_a_mention_from_notifying_anyone_whatever_markdown_is_around_it(self):
        found = {**F1, 'headline': 'Ask ` @alice ` or \\@bob', 'take': 'Or `@carol`.'}

        self.post([found], [{'path': 'src/sim.ts', 'line': 42}])

        added, _ = self.review()
        body = added['threads'][0]['body']
        # GitHub links a mention only when a login's first character follows the @.
        self.assertNotRegex(body, r'@[A-Za-z0-9]')
        self.assertIn('**Ask ` @\u2060alice ` or \\@\u2060bob**', body)

    def test_says_a_resolved_thread_is_still_found_before_the_commentary(self):
        self.assertEqual(self.reply('Alice said it was fixed in abc1234.', resolved=True),
                         '🤖 `still found` `hhhhhhh`\n\n> Alice said it was fixed in abc1234.'
                         f'\n\n{MARKER}')

    def test_quotes_every_line(self):
        self.assertIn('> One.\n>\n> Two.\n', self.reply('One.\n\nTwo.'))

    def test_keeps_mentions_from_notifying_and_html_from_hiding_text(self):
        body = self.reply('@alice and @org/team-a said so. <!-- hidden --> <b>x</b> Mail a@b.com.')

        self.assertIn('> @\u2060alice and @\u2060org/team-a said so. &lt;!-- hidden --> &lt;b>x&lt;/b> Mail a@\u2060b.com.', body)
