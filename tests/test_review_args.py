import json
import shlex
import subprocess
import sys
import unittest

from review_case import REVIEW

INPUTS = '/runner/temp/pack-review.abc123'


class ArgsTests(unittest.TestCase):
    """The arguments the review action hands claude-code-action for the agent."""

    def args(self, *extra):
        run = subprocess.run([sys.executable, str(REVIEW / 'args.py'), '--inputs', INPUTS, *extra],
                             capture_output=True, text=True, check=True)
        self.assertEqual(run.stdout.count('\n'), 1)
        return shlex.split(run.stdout)

    def flag(self, args, name):
        return args[args.index(name) + 1]

    def test_loads_the_skill_and_validates_the_answer_against_the_schema(self):
        args = self.args()

        self.assertEqual(self.flag(args, '--plugin-dir'), str(REVIEW.parent))
        self.assertEqual(json.loads(self.flag(args, '--json-schema')),
                         json.loads((REVIEW / 'findings.schema.json').read_text()))

    def test_gives_the_agent_no_mcp_servers(self):
        args = self.args()

        self.assertNotIn('--mcp-config', args)
        self.assertIn('--strict-mcp-config', args)

    def test_gives_the_agent_tools_that_only_read_the_checkout_and_the_diff(self):
        args = self.args()

        self.assertEqual(self.flag(args, '--tools'), 'Read,Glob,Grep,Agent')
        self.assertEqual(self.flag(args, '--allowedTools'), 'Read,Glob,Grep,Agent')
        self.assertEqual(self.flag(args, '--add-dir'), INPUTS)
        self.assertEqual(self.flag(args, '--disallowedTools'), 'Read(./.git/**)')
        self.assertIn('--restricted', args)

    def test_passes_a_model_when_given_one(self):
        self.assertEqual(self.flag(self.args('--model', 'opus'), '--model'), 'opus')
        self.assertNotIn('--model', self.args('--model', ''))

    def test_quotes_each_value_whole_so_any_shell_style_parser_reads_it_the_same(self):
        line = subprocess.run([sys.executable, str(REVIEW / 'args.py'), '--inputs', INPUTS],
                              capture_output=True, text=True, check=True).stdout
        for value in shlex.split(line):
            quoted = shlex.quote(value)
            self.assertTrue(quoted == value or (quoted.startswith("'") and quoted.count("'") == 2), value[:60])


class SettingsTests(unittest.TestCase):
    """The settings the review agent runs with."""

    def test_runs_subagents_in_the_foreground_so_their_answers_arrive_before_the_agent_goes_on(self):
        run = subprocess.run([sys.executable, str(REVIEW / 'args.py'), '--inputs', INPUTS], capture_output=True,
                             text=True, check=True)
        args = shlex.split(run.stdout)

        settings = json.loads(args[args.index('--settings') + 1])
        self.assertEqual(settings, {'env': {'CLAUDE_CODE_DISABLE_BACKGROUND_TASKS': '1'}})
