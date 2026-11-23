import shlex

from review_case import REVIEW
from test_review_pairing import PairingCase

BASE, HEAD = 'b' * 40, 'h' * 40
ANSWERS = '/runner/temp/runs/pack-review-answers'
CLI = f'python3 {REVIEW.parent}/src/cli.py'


class StartTests(PairingCase):
    """The review job's agent runs the pack-findings skill, as a local review does, from the review's own checkout,
    allowed only the commands the skill runs."""

    def start(self, *extra):
        run = self.script('start', '--base', BASE, '--head', HEAD, '--answers', ANSWERS, *extra)
        self.assertEqual(run.returncode, 0, run.stderr)
        return self.outputs()

    def args(self, *extra):
        return shlex.split(self.start(*extra)['claude-args'])

    def flag(self, args, name):
        return args[args.index(name) + 1]

    def test_asks_for_the_pack_findings_skill_on_the_reviewed_range(self):
        self.assertEqual(self.start()['prompt'],
                         f'Use the pack-findings skill on the commit range {BASE}..{HEAD}, with the checkout CLI.')

    def test_loads_the_skill_from_the_reviews_checkout(self):
        self.assertEqual(self.flag(self.args(), '--plugin-dir'), str(REVIEW.parent))

    def test_allows_only_the_skill_and_the_commands_it_runs(self):
        args = self.args()

        self.assertEqual(self.flag(args, '--tools'), 'Read,Glob,Grep,Write,Bash,Agent,Skill')
        self.assertEqual(self.flag(args, '--allowedTools').split(','), [
            'Skill(context-packs:pack-findings)', f'Bash({CLI} review:*)', f'Bash({CLI} docs)',
            'Bash(git rev-parse:*)', 'Bash(git status:*)', f'Edit(/{ANSWERS}/**)'])
        self.assertEqual(self.flag(args, '--disallowedTools'), 'Read(./.git/**)')
        self.assertIn('--restricted', args)

    def test_lets_the_agent_write_only_in_the_answers_folder(self):
        # A headless run writes outside its working directory only with both: the folder added, and an Edit rule for it.
        args = self.args()

        self.assertEqual(self.flag(args, '--add-dir'), ANSWERS)
        self.assertEqual([rule for rule in self.flag(args, '--allowedTools').split(',') if rule.startswith('Edit')],
                         [f'Edit(//{ANSWERS[1:]}/**)'])

    def test_gives_the_agent_no_mcp_server_and_no_answer_schema(self):
        args = self.args()

        self.assertIn('--strict-mcp-config', args)
        self.assertNotIn('--mcp-config', args)
        self.assertNotIn('--json-schema', args)

    def test_passes_a_model_when_given_one(self):
        self.assertEqual(self.flag(self.args('--model', 'opus'), '--model'), 'opus')
        self.output.write_text('')
        self.assertNotIn('--model', self.args('--model', ''))

    def test_quotes_each_value_whole_so_any_shell_style_parser_reads_it_the_same(self):
        for value in self.args():
            quoted = shlex.quote(value)
            self.assertTrue(quoted == value or (quoted.startswith("'") and quoted.count("'") == 2), value[:60])
