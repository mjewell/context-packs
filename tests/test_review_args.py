import json
import shlex
import subprocess
import sys
import unittest

from review_case import REVIEW

HEAD = 'h' * 40
TOOLS = ['mcp__pack-review__read_comments', 'mcp__pack-review__open_thread', 'mcp__pack-review__reply']


class ArgsTests(unittest.TestCase):
    """The arguments the review action hands claude-code-action for the agent."""

    def args(self, *extra):
        run = subprocess.run([sys.executable, str(REVIEW / 'args.py'), '--pr', '7', '--head', HEAD, *extra],
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

    def test_gives_the_agent_the_review_tools_for_its_pr(self):
        args = self.args()

        config = json.loads(self.flag(args, '--mcp-config'))
        self.assertEqual(config, {'mcpServers': {'pack-review': {
            'command': 'python3', 'args': [str(REVIEW / 'tools.py'), '--pr', '7', '--head', HEAD]}}})
        self.assertIn('--strict-mcp-config', args)

    def test_gives_the_agent_tools_that_read_the_checkout_and_its_review_tools_and_no_shell_but_git(self):
        args = self.args()

        self.assertEqual(self.flag(args, '--tools'), 'Read,Glob,Grep,Bash,Agent')
        self.assertEqual(self.flag(args, '--allowedTools').split(','),
                         ['Read', 'Glob', 'Grep', 'Agent', 'Bash(git diff:*)', 'Bash(git log:*)', 'Bash(git show:*)',
                          *TOOLS])
        self.assertEqual(self.flag(args, '--disallowedTools'), 'Read(./.git/**)')
        self.assertIn('--restricted', args)

    def test_passes_a_model_when_given_one(self):
        self.assertEqual(self.flag(self.args('--model', 'opus'), '--model'), 'opus')
        self.assertNotIn('--model', self.args('--model', ''))

    def test_quotes_each_value_whole_so_any_shell_style_parser_reads_it_the_same(self):
        line = subprocess.run([sys.executable, str(REVIEW / 'args.py'), '--pr', '7', '--head', HEAD],
                              capture_output=True, text=True, check=True).stdout
        for value in shlex.split(line):
            quoted = shlex.quote(value)
            self.assertTrue(quoted == value or (quoted.startswith("'") and quoted.count("'") == 2), value[:60])
