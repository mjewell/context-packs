import json
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest

from review_case import REVIEW
from test_review_reads import Transcript

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


class HookTests(unittest.TestCase):
    """The hooks the arguments install: run as Claude Code runs a hook's command, through a shell with its input on
    stdin, each reaches its read gate with the folder holding docs.txt."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='context-packs-hooks-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.inputs, self.checkout = self.root / 'pack-review.abc123', self.root / 'checkout'
        self.inputs.mkdir()
        (self.inputs / 'docs.txt').write_text('AGENTS.md\n')
        self.main = Transcript(self.root / 'session.jsonl', self.checkout, sidechain=False)
        run = subprocess.run([sys.executable, str(REVIEW / 'args.py'), '--inputs', str(self.inputs)],
                             capture_output=True, text=True, check=True)
        args = shlex.split(run.stdout)
        self.hooks = json.loads(args[args.index('--settings') + 1])['hooks']

    def run_hook(self, event, input):
        [entry] = self.hooks[event]
        [hook] = entry['hooks']
        self.assertEqual(hook['type'], 'command')
        run = subprocess.run(hook['command'], shell=True, input=json.dumps(input), capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        return entry, json.loads(run.stdout)

    def test_holds_the_answer_until_the_docs_are_read(self):
        entry, decision = self.run_hook('PreToolUse', {
            'hook_event_name': 'PreToolUse', 'cwd': str(self.checkout), 'transcript_path': str(self.main.path),
            'tool_name': 'StructuredOutput', 'tool_input': {'findings': []}})

        self.assertEqual(entry['matcher'], 'StructuredOutput')
        self.assertEqual(decision['hookSpecificOutput']['permissionDecision'], 'deny')

    def test_holds_each_subagent_until_its_docs_are_read(self):
        subagent = Transcript(self.root / 'session' / 'subagents' / 'agent-1.jsonl', self.checkout, sidechain=True)
        subagent.prompt(f'Check {self.checkout / "AGENTS.md"} against the diff.')

        _, decision = self.run_hook('SubagentStop', {
            'hook_event_name': 'SubagentStop', 'cwd': str(self.checkout), 'transcript_path': str(self.main.path),
            'agent_transcript_path': str(subagent.path)})

        self.assertEqual(decision['decision'], 'block')
