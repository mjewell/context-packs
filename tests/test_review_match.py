import json
import re

from review_case import ReviewCase


def finding(headline, path='src/sim.ts', line=42, kind='deviates'):
    return {'kind': kind, 'headline': headline, 'rules': [], 'spots': [{'path': path, 'line': line, 'follows': False}],
            'deliberate': [], 'exemplars': [], 'take': 'Move it to content.'}


def opened(id, found, replies=(), resolved=False):
    """A pack-review thread as threads.py prints it: its first comment's text is GitHub's bodyText of the comment
    that opened it, which says what the finding is."""
    first = {'id': f'{id}_c', 'author': 'github-actions', 'at': '2026-11-01T10:00:00Z',
             'text': f"pack-review found a deviation here at abc1234: {found['headline']}\n{found['take']}"}
    return {'id': id, 'path': found['spots'][0]['path'], 'line': found['spots'][0]['line'], 'resolved': resolved,
            'comments': [first, *replies]}


F1 = finding('A game number in sim code')
F3 = finding('A second RNG', path='src/rng.ts', line=17)
ALICE = {'id': 'RC_2', 'author': 'alice', 'at': '2026-11-02T10:00:00Z', 'text': 'Kept on purpose: the balance spec.'}


class MatchCase(ReviewCase):
    """The match job, between find and post: the find job's report, and pack-review's threads as threads.py prints
    them."""

    def setUp(self):
        super().setUp()
        self.output = self.root / 'github-output.txt'
        self.output.write_text('')
        self.env['GITHUB_OUTPUT'] = str(self.output)

    def given(self, findings, threads):
        (self.root / 'report.json').write_text(json.dumps({'base': 'b' * 40, 'base_ref': 'main', 'head': 'h' * 40,
                                                           'findings': findings, 'unread': [],
                                                           'unread_diffs': []}))
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
                           '--out', 'match.json')

    def matched(self):
        return json.loads((self.root / 'match.json').read_text())


class PromptTests(MatchCase):
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

    def test_runs_the_agent_with_no_tools_and_the_pairs_schema(self):
        self.given([F1], [opened('T_1', F1)])

        args = self.prompt()['claude-args']

        self.assertIn("--tools ''", args)
        self.assertIn('--strict-mcp-config', args)
        self.assertIn('"pairs"', args)

    def test_needs_no_agent_when_there_are_no_threads_or_no_findings(self):
        for findings, threads in (([F1], []), ([], [opened('T_1', F1)])):
            with self.subTest(findings=len(findings), threads=len(threads)):
                self.output.write_text('')
                self.given(findings, threads)

                self.assertEqual(self.prompt()['needed'], 'false')


class CheckTests(MatchCase):
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
                self.assertFalse((self.root / 'match.json').exists())

    def test_refuses_an_answer_that_isnt_pairs(self):
        run = self.check('')

        self.assertEqual(run.returncode, 1)
        self.assertIn('no pairs', run.stderr)


BOB = {'id': 'RC_3', 'hidden': 'author lacks write access'}
EARLIER = {'id': 'RC_4', 'author': 'github-actions', 'at': '2026-11-03T10:00:00Z',
           'text': 'Alice says this is deliberate, per the balance spec.'}


class CommentCase(MatchCase):
    """The match job after pairing: F1 continues T1, where Alice explained it and Bob, who can't write, replied."""

    def setUp(self):
        super().setUp()
        self.given([F1, F3], [opened('T_1', F1, replies=[ALICE, BOB]), opened('T_2', finding('Old'), resolved=True)])
        (self.root / 'match.json').write_text(json.dumps({'pairs': [{'finding': 0, 'thread': 'T_1'}]}))

    def comment_prompt(self):
        run = self.script('pairing', 'comment-prompt', '--report', 'report.json', '--threads', 'threads.json',
                          '--match', 'match.json')
        self.assertEqual(run.returncode, 0, run.stderr)
        return self.outputs()

    def comment_check(self, commentary=None):
        args = []
        if commentary is not None:
            (self.root / 'commentary.json').write_text(
                commentary if isinstance(commentary, str) else json.dumps({'commentary': commentary}))
            args = ['--commentary', 'commentary.json']
        return self.script('pairing', 'comment-check', '--match', 'match.json', *args)


class CommentPromptTests(CommentCase):
    """The commentary agent gets each paired finding with its thread's replies as trust.py filters them."""

    def test_gives_each_paired_finding_with_its_threads_replies(self):
        prompt = self.comment_prompt()['prompt']

        self.assertIn('A game number in sim code', prompt)
        self.assertIn('Kept on purpose: the balance spec.', prompt)
        self.assertIn('alice', prompt)
        self.assertIn('author lacks write access', prompt)
        self.assertNotIn('A second RNG', prompt)
        self.assertNotIn('Old', prompt)

    def test_gives_pack_reviews_earlier_replies_so_it_doesnt_repeat_them(self):
        threads = json.loads((self.root / 'threads.json').read_text())
        threads[0]['comments'].append(EARLIER)
        (self.root / 'threads.json').write_text(json.dumps(threads))

        self.assertIn('Alice says this is deliberate', self.comment_prompt()['prompt'])

    def test_runs_the_agent_with_no_tools_and_the_commentary_schema(self):
        args = self.comment_prompt()['claude-args']

        self.assertIn("--tools ''", args)
        self.assertIn('"commentary"', args)

    def test_needs_no_agent_when_nothing_is_paired(self):
        (self.root / 'match.json').write_text(json.dumps({'pairs': []}))

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
                (self.root / 'match.json').write_text(json.dumps({'pairs': [{'finding': 0, 'thread': 'T_1'}]}))

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
