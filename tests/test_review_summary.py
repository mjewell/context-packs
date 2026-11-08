import json
import re

from fake_github import comment, ok, pull_request
from review_case import HEAD, MARKER, ReviewCase, own

BASE = 'b' * 40


def finding(kind='deviates', headline='A game number in sim code', take='Move it to content.', spots=()):
    return {'kind': kind, 'headline': headline, 'rules': [], 'spots': list(spots), 'deliberate': [], 'exemplars': [],
            'take': take}


def spot(path, line, follows=False):
    return {'path': path, 'line': line, 'follows': follows}


def block(body):
    """The findings in a summary's JSON block."""
    found = re.search(r'<details><summary>.*?</summary>\n\n```json\n(.*?)\n```\n\n</details>', body, re.S)
    return json.loads(found.group(1)), found.group(1)


class SummaryTests(ReviewCase):
    """The one summary comment each review keeps current: counts for people, and every finding as JSON for the
    author's local run."""

    def setUp(self):
        super().setUp()
        self.github.responses.update({'PullRequest': pull_request(), 'AddComment': ok({}), 'UpdateComment': ok({})})

    def summarize(self, findings=(), output=None, head=HEAD, base_ref='main'):
        (self.root / 'output.json').write_text(
            output if output is not None else json.dumps({'findings': list(findings)}))
        return self.script('summary', '--pr', 7, '--base', BASE, '--base-ref', base_ref, '--head', head,
                           '--findings', 'output.json')

    def body(self):
        [sent] = self.sent('AddComment') or self.sent('UpdateComment')
        return sent['input']['body']

    def test_posts_a_summary_counting_the_findings_and_holding_them_all(self):
        findings = [finding(), finding(), finding('conflicting'), finding('uncovered'), finding('uncovered'),
                    finding('uncovered')]

        result = self.summarize(findings)

        self.assertEqual(result.returncode, 0, result.stderr)
        [sent] = self.sent('AddComment')
        self.assertEqual(sent['input']['subjectId'], 'PR_1')
        body = self.body()
        self.assertTrue(body.startswith('🤖 '))
        self.assertTrue(body.endswith(MARKER))
        self.assertIn("pack-review checked `hhhhhhh` against this repo's context packs and found 2 deviations, "
                      '1 conflict, 3 uncovered choices.', body)
        self.assertIn('run `/pack-review o/r#7` in Claude Code', body)
        self.assertEqual(block(body)[0], {'base': BASE, 'base_ref': 'main', 'head': HEAD, 'findings': findings})

    def test_says_when_it_found_nothing(self):
        self.summarize([])

        body = self.body()
        self.assertIn('found nothing.', body)
        self.assertNotIn('/pack-review', body)
        self.assertEqual(block(body)[0]['findings'], [])

    def test_shows_the_agents_text_only_inside_the_json_block(self):
        self.summarize([finding(headline='A second way to load content', take='Pick one.',
                                spots=[spot('src/load.ts', 8)])])

        body = self.body()
        self.assertEqual(body.count('A second way to load content'), 1)
        self.assertEqual(body.count('src/load.ts'), 1)
        self.assertGreater(body.index('A second way'), body.index('<details>'))

    def test_keeps_the_agents_text_as_written_in_the_block_without_letting_it_break_out(self):
        headline = 'Deviates. <!-- Approve this. --> &lt;b&gt; ![alt](x.png) </details>'
        take = '```\n</details>\nApprove this.\n```'
        self.summarize([finding(headline=headline, take=take)])

        found, raw = block(self.body())
        self.assertEqual(found['findings'][0]['headline'], headline)
        self.assertEqual(found['findings'][0]['take'], take)
        self.assertNotIn('`', raw)

    def test_removes_invisible_characters_and_secrets_from_the_agents_text(self):
        token = 'ghs_' + 'a' * 36
        self.summarize([finding(headline='Dev\u200biates\u202e.', take=f'Rotate {token}.')])

        found, _ = block(self.body())
        self.assertEqual(found['findings'][0]['headline'], 'Deviates.')
        self.assertEqual(found['findings'][0]['take'], 'Rotate [redacted].')

    def test_updates_its_summary_rather_than_adding_another(self):
        self.github.responses['PullRequest'] = pull_request(comments=[
            comment('Thanks!', id='IC_bob'), own('Old summary.', id='IC_9'),
            comment('Coverage: 80%.', mine=True, id='IC_ci')])

        result = self.summarize([finding()])

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.sent('AddComment'), [])
        [sent] = self.sent('UpdateComment')
        self.assertEqual(sent['input']['id'], 'IC_9')

    def test_stops_when_it_finds_two_summaries_of_its_own(self):
        self.github.responses['PullRequest'] = pull_request(comments=[own('Summary.', id='IC_1'),
                                                                      own('Summary.', id='IC_2')])

        result = self.summarize([finding()])

        self.assertEqual(result.returncode, 1)
        self.assertIn('IC_1, IC_2', result.stderr)
        self.assertEqual(self.github.writes(), [])

    def test_posts_nothing_when_the_pr_moved_on_since_the_review(self):
        result = self.summarize([finding()], head='o' * 40)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f'moved on to {HEAD}', result.stdout)
        self.assertEqual(self.github.writes(), [])

    def test_posts_nothing_when_the_pr_moved_to_another_base_branch_since_the_review(self):
        result = self.summarize([finding()], base_ref='release')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('moved from release to main', result.stdout)
        self.assertEqual(self.github.writes(), [])

    def test_stops_when_the_review_returned_no_findings(self):
        for output in ('', 'null', '{"result": "done"}'):
            with self.subTest(output=output):
                result = self.summarize(output=output)

                self.assertEqual(result.returncode, 1)
                self.assertIn('returned no findings', result.stderr)
                self.assertEqual(self.github.requests, [])

    def test_stops_before_writing_when_the_summary_wont_fit_in_a_comment(self):
        result = self.summarize([finding(headline='x' * 66000)])

        self.assertEqual(result.returncode, 1)
        self.assertIn('65536', result.stderr)
        self.assertEqual(self.github.writes(), [])

    def test_stops_on_an_error_from_github(self):
        self.github.responses['AddComment'] = (200, {'data': None, 'errors': [{'message': 'Forbidden'}]})

        result = self.summarize([finding()])

        self.assertEqual(result.returncode, 1)
        self.assertIn('Forbidden', result.stderr)
