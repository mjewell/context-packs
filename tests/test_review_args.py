import json
import shlex
import subprocess
import sys
import unittest

from review_case import REVIEW

INPUTS = '/runner/temp/pack-review.abc123'
BASE, HEAD = 'b' * 40, 'h' * 40
COMMAND = [sys.executable, str(REVIEW / 'args.py'), '--inputs', INPUTS, '--base', BASE, '--head', HEAD]


class ArgsTests(unittest.TestCase):
    """The arguments the merge action hands claude-code-action for the agent that merges the finders' answers."""

    def args(self, *extra):
        run = subprocess.run([*COMMAND, *extra], capture_output=True, text=True, check=True)
        self.assertEqual(run.stdout.count('\n'), 1)
        return shlex.split(run.stdout)

    def flag(self, args, name):
        return args[args.index(name) + 1]

    def test_loads_the_skill_and_validates_the_answer_against_the_schema(self):
        args = self.args()

        self.assertEqual(self.flag(args, '--plugin-dir'), str(REVIEW.parent))
        self.assertEqual(json.loads(self.flag(args, '--json-schema')),
                         json.loads((REVIEW / 'findings.schema.json').read_text()))

    def test_gives_the_agent_only_the_git_server_for_the_change(self):
        args = self.args()

        self.assertEqual(json.loads(self.flag(args, '--mcp-config')), {'mcpServers': {'git': {
            'type': 'stdio', 'command': sys.executable,
            'args': [str(REVIEW / 'git_server.py'), '--base', BASE, '--head', HEAD]}}})
        self.assertEqual(args.count('--mcp-config'), 1)
        self.assertIn('--strict-mcp-config', args)

    def test_gives_the_agent_tools_that_only_read_the_checkout_and_the_change_and_no_subagents(self):
        args = self.args()

        self.assertEqual(self.flag(args, '--tools'), 'Read,Glob,Grep')
        # mcp__git allows every tool on the git server. It must not start with mcp__github, or claude-code-action adds
        # its own GitHub servers.
        self.assertEqual(self.flag(args, '--allowedTools'), 'Read,Glob,Grep,mcp__git')
        self.assertEqual(self.flag(args, '--add-dir'), INPUTS)
        self.assertEqual(self.flag(args, '--disallowedTools'), 'Read(./.git/**)')
        self.assertIn('--restricted', args)

    def test_passes_a_model_when_given_one(self):
        self.assertEqual(self.flag(self.args('--model', 'opus'), '--model'), 'opus')
        self.assertNotIn('--model', self.args('--model', ''))

    def test_quotes_each_value_whole_so_any_shell_style_parser_reads_it_the_same(self):
        line = subprocess.run(COMMAND, capture_output=True, text=True, check=True).stdout
        for value in shlex.split(line):
            quoted = shlex.quote(value)
            self.assertTrue(quoted == value or (quoted.startswith("'") and quoted.count("'") == 2), value[:60])

