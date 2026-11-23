import json
import re

from review_case import ReviewCase


def finding(headline, path='src/sim.ts', line=42, kind='deviation'):
    return {'kind': kind, 'headline': headline, 'rules': [], 'spots': [{'path': path, 'line': line, 'follows': False}],
            'deliberate': [], 'exemplars': [], 'take': 'Move it to content.'}


def opened(id, found, replies=(), resolved=False):
    """A pack-review thread as threads.py prints it: its first comment's text is GitHub's bodyText of the comment
    that opened it, which says what the finding is."""
    first = {'id': f'{id}_c', 'author': 'github-actions', 'at': '2026-11-01T10:00:00Z',
             'text': f"pack-review found a deviation here at abc1234: {found['headline']}\n{found['take']}",
             'ours': True}
    return {'id': id, 'path': found['spots'][0]['path'], 'line': found['spots'][0]['line'], 'resolved': resolved,
            'comments': [first, *replies]}


F1 = finding('A game number in sim code')
F3 = finding('A second RNG', path='src/rng.ts', line=17)
ALICE = {'id': 'RC_2', 'author': 'alice', 'at': '2026-11-02T10:00:00Z', 'text': 'Kept on purpose: the balance spec.',
         'ours': False}


class PairingCase(ReviewCase):
    """The pairing job, between review and post: the review job's report, and pack-review's threads as threads.py prints
    them."""

    def setUp(self):
        super().setUp()
        self.output = self.root / 'github-output.txt'
        self.output.write_text('')
        self.env['GITHUB_OUTPUT'] = str(self.output)

    def given(self, findings, threads, head='h' * 40):
        (self.root / 'report.json').write_text(json.dumps({'base': 'b' * 40, 'base_ref': 'main', 'head': head,
                                                           'findings': findings}))
        (self.root / 'threads.json').write_text(json.dumps(threads))

    def outputs(self):
        """The step outputs written to GITHUB_OUTPUT, each value whole."""
        text, found = self.output.read_text(), {}
        for name, delimiter, value in re.findall(r'^(\w[\w-]*)<<(\S+)\n(.*?)\n\2$', text, re.S | re.M):
            found[name] = value
        return found

    def prompt(self):
        run = self.script('pairing', 'pair-prompt', '--report', 'report.json', '--threads', 'threads.json')
        self.assertEqual(run.returncode, 0, run.stderr)
        return self.outputs()

    def check(self, pairs=None):
        args = ['--pairs', 'pairs.json'] if pairs is not None else []
        if pairs is not None:
            (self.root / 'pairs.json').write_text(pairs if isinstance(pairs, str) else json.dumps({'pairs': pairs}))
        return self.script('pairing', 'pair-check', '--report', 'report.json', '--threads', 'threads.json', *args,
                           '--out', 'paired.json')

    def matched(self):
        return json.loads((self.root / 'paired.json').read_text())


class PromptTests(PairingCase):
    """The pairing agent gets this run's findings and the findings pack-review's threads were opened for, and no
    comment anyone wrote, so no comment can bias which thread a finding lands in."""

    def test_gives_the_new_findings_and_each_threads_opening_comment_and_no_reply(self):
        self.given([F1, F3], [opened('T_1', finding('A magic number in the sim'), replies=[ALICE])])

        outputs = self.prompt()

        self.assertEqual(outputs['needed'], 'true')
        prompt = outputs['prompt']
        self.assertIn('A game number in sim code', prompt)
        self.assertIn('A second RNG', prompt)
        self.assertIn('"T_1" on src/sim.ts:42: "pack-review found a deviation here at abc1234: A magic number in the '
                      'sim', prompt)
        self.assertNotIn('balance spec', prompt)
        self.assertNotIn('alice', prompt)

    def test_runs_the_agent_with_only_the_tool_that_returns_its_answer_and_the_pairs_schema(self):
        self.given([F1], [opened('T_1', F1)])

        args = self.prompt()['claude-args']

        # Claude Code returns an answer to --json-schema through the StructuredOutput tool, which --tools '' removes.
        self.assertIn('--tools StructuredOutput', args)
        self.assertIn('--strict-mcp-config', args)
        self.assertIn('"pairs"', args)

    def test_needs_no_agent_when_there_are_no_threads_or_no_findings(self):
        for findings, threads in (([F1], []), ([], [opened('T_1', F1)])):
            with self.subTest(findings=len(findings), threads=len(threads)):
                self.output.write_text('')
                self.given(findings, threads)

                self.assertEqual(self.prompt()['needed'], 'false')


class CheckTests(PairingCase):
    """The post job gets only pairs that name a new finding and one of pack-review's threads, each at most once."""

    def setUp(self):
        super().setUp()
        self.given([F1, F3], [opened('T_1', F1), opened('T_2', F3, resolved=True)])

    def test_writes_the_pairs_for_the_post_job(self):
        run = self.check([{'finding': 0, 'thread': 'T_1'}])

        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(self.matched(), {'pairs': [{'finding': 0, 'thread': 'T_1'}]})

    def test_writes_no_pairs_when_the_agent_didnt_run(self):
        self.assertEqual(self.check().returncode, 0)
        self.assertEqual(self.matched(), {'pairs': []})

    def test_refuses_pairs_that_name_no_finding_or_another_thread_or_repeat_one(self):
        for pairs, says in (([{'finding': 2, 'thread': 'T_1'}], 'finding 2'),
                            ([{'finding': 0, 'thread': 'T_9'}], 'T_9'),
                            ([{'finding': 0, 'thread': 'T_1'}, {'finding': 0, 'thread': 'T_2'}], 'finding 0'),
                            ([{'finding': 0, 'thread': 'T_1'}, {'finding': 1, 'thread': 'T_1'}], 'T_1')):
            with self.subTest(pairs=pairs):
                run = self.check(pairs)

                self.assertEqual(run.returncode, 1)
                self.assertIn(says, run.stderr)
                self.assertFalse((self.root / 'paired.json').exists())

    def test_refuses_an_answer_that_isnt_pairs(self):
        run = self.check('')

        self.assertEqual(run.returncode, 1)
        self.assertIn('no pairs', run.stderr)


BOB = {'id': 'RC_3', 'hidden': 'author lacks write access'}
RELAYED = {'id': 'RC_4', 'author': 'github-actions', 'at': '2026-11-03T10:00:00Z',
           'text': '🤖 abc1234\n\nAlice says this is deliberate.', 'ours': True}
LATER = {'id': 'RC_5', 'author': 'alice', 'at': '2026-11-04T10:00:00Z', 'text': 'Fixed in the last push.', 'ours': False}


class CommentCase(PairingCase):
    """The pairing job once the pairs are checked: F1 continues T1. The review ran again at the head."""

    def setUp(self):
        super().setUp()
        self.thread([ALICE, BOB])
        (self.root / 'paired.json').write_text(json.dumps({'pairs': [{'finding': 0, 'thread': 'T_1'}]}))

    def thread(self, replies):
        self.given([F1, F3], [opened('T_1', F1, replies=replies), opened('T_2', finding('Old'), resolved=True)],
                   head='e' * 40)

    def comment_prompt(self):
        run = self.script('pairing', 'comment-prompt', '--report', 'report.json', '--threads', 'threads.json',
                          '--paired', 'paired.json')
        self.assertEqual(run.returncode, 0, run.stderr)
        return self.outputs()

    def comment_check(self, commentary=None):
        args = []
        if commentary is not None:
            (self.root / 'commentary.json').write_text(
                commentary if isinstance(commentary, str) else json.dumps({'commentary': commentary}))
            args = ['--commentary', 'commentary.json']
        return self.script('pairing', 'comment-check', '--paired', 'paired.json', *args)


class CommentPromptTests(CommentCase):
    """The commentary agent gets every paired finding with its thread, told which comments are its own and which
    replies came after its last one, so it can tell what it already said."""

    def test_gives_each_paired_finding_with_its_threads_replies_and_the_commit_it_was_found_at(self):
        prompt = self.comment_prompt()['prompt']

        self.assertIn('A game number in sim code', prompt)
        self.assertIn(f"ran again at {'e' * 7} and still finds each finding", prompt)
        self.assertIn('author lacks write access', prompt)
        self.assertNotIn('A second RNG', prompt)
        self.assertNotIn('Old', prompt)

    def test_marks_its_own_comments_as_its_own(self):
        self.thread([ALICE, RELAYED])

        prompt = self.comment_prompt()['prompt']

        self.assertIn('- you (pack-review), opening the thread: "pack-review found a deviation', prompt)
        self.assertIn('- you (pack-review), at 2026-11-03T10:00:00Z: "🤖 abc1234', prompt)
        self.assertNotIn('github-actions', prompt)

    def test_marks_the_replies_after_its_last_comment_as_new(self):
        self.thread([ALICE, RELAYED, LATER])

        prompt = self.comment_prompt()['prompt']

        self.assertIn('- alice at 2026-11-02T10:00:00Z: "Kept on purpose: the balance spec."', prompt)
        self.assertIn('- alice at 2026-11-04T10:00:00Z, new since your last comment: "Fixed in the last push."',
                      prompt)

    def test_says_why_a_comment_was_minimized(self):
        self.thread([{**ALICE, 'minimized': 'outdated'}, {**RELAYED, 'minimized': 'resolved'}])

        prompt = self.comment_prompt()['prompt']

        self.assertIn('- alice at 2026-11-02T10:00:00Z, minimized as outdated: "Kept on purpose', prompt)
        self.assertIn('- you (pack-review), at 2026-11-03T10:00:00Z, minimized as resolved: "🤖 abc1234', prompt)

    def test_asks_about_a_paired_thread_even_with_no_new_reply(self):
        self.thread([ALICE, RELAYED])

        self.assertEqual(self.comment_prompt()['needed'], 'true')

    def test_runs_the_agent_with_only_the_tool_that_returns_its_answer_and_the_commentary_schema(self):
        args = self.comment_prompt()['claude-args']

        self.assertIn('--tools StructuredOutput', args)
        self.assertIn('"commentary"', args)

    def test_needs_no_agent_when_nothing_is_paired(self):
        (self.root / 'paired.json').write_text(json.dumps({'pairs': []}))

        self.assertEqual(self.comment_prompt()['needed'], 'false')


class CommentCheckTests(CommentCase):
    """The post job gets commentary only on paired findings, one each, cleaned like the findings."""

    def test_adds_the_commentary_to_the_pairs(self):
        run = self.comment_check([{'finding': 0, 'text': 'Alice says it\u200b is deliberate. ghp_' + 'a' * 36}])

        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(self.matched(), {'pairs': [{'finding': 0, 'thread': 'T_1'}],
                                          'commentary': [{'finding': 0, 'text': 'Alice says it is deliberate. '
                                                                                '[redacted]'}]})

    def test_adds_no_commentary_when_the_agent_didnt_run_or_had_nothing_to_say(self):
        for commentary in (None, []):
            with self.subTest(commentary=commentary):
                (self.root / 'paired.json').write_text(json.dumps({'pairs': [{'finding': 0, 'thread': 'T_1'}]}))

                self.assertEqual(self.comment_check(commentary).returncode, 0)
                self.assertEqual(self.matched()['commentary'], [])

    def test_refuses_commentary_on_an_unpaired_finding_twice_on_one_or_empty(self):
        for commentary, says in (([{'finding': 1, 'text': 'Hi.'}], 'finding 1'),
                                 ([{'finding': 0, 'text': 'A.'}, {'finding': 0, 'text': 'B.'}], 'finding 0'),
                                 ([{'finding': 0, 'text': ' \u200b '}], 'empty')):
            with self.subTest(commentary=commentary):
                run = self.comment_check(commentary)

                self.assertEqual(run.returncode, 1)
                self.assertIn(says, run.stderr)
                self.assertNotIn('commentary', self.matched())

    def test_refuses_an_answer_that_isnt_commentary(self):
        run = self.comment_check('{}')

        self.assertEqual(run.returncode, 1)
        self.assertIn('no commentary', run.stderr)
