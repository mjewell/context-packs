import json
import shlex

from review_case import REVIEW, ReviewCase
from test_review_match import MatchCase

DOCS = 'context-packs/project/a.md\ncontext-packs/project/b.md\n\ncontext-packs/gen/core/c.md\n'


class UnitsCase(MatchCase):
    """A checkout with an instruction file holding the context-packs block, and the docs `context-packs docs` lists,
    by pack."""

    def setUp(self):
        super().setUp()
        (self.root / 'AGENTS.md').write_text('# Repo\n\n<!-- context-packs:start -->\nrules\n<!-- context-packs:end -->\n')
        (self.root / 'docs.txt').write_text(DOCS)

    def units(self, *args):
        run = self.script('units', *args)
        self.assertEqual(run.returncode, 0, run.stderr)
        return self.outputs()


class ListTests(UnitsCase):
    """The units job lists one unit per finder: the instruction file, then each pack's docs."""

    def test_lists_the_instruction_file_and_each_packs_docs_as_units(self):
        self.assertEqual(json.loads(self.units('list', '--docs', 'docs.txt')['units']), [0, 1, 2])

    def test_uses_claude_md_when_it_holds_the_block(self):
        (self.root / 'AGENTS.md').unlink()
        (self.root / 'CLAUDE.md').write_text('<!-- context-packs:start -->\n<!-- context-packs:end -->\n')

        outputs = self.units('prompt', '--docs', 'docs.txt', '--unit', '0', '--base', 'b' * 40, '--head', 'h' * 40)

        self.assertIn('- `CLAUDE.md`', outputs['prompt'])


class PromptTests(UnitsCase):
    """Each finder gets the unit prompt the skill pins, with its own docs and the git server."""

    def prompt(self, unit):
        return self.units('prompt', '--docs', 'docs.txt', '--unit', str(unit), '--base', 'b' * 40, '--head', 'h' * 40)

    def test_fills_the_skills_unit_prompt_with_the_units_docs(self):
        prompt = self.prompt(1)['prompt']

        self.assertTrue(prompt.startswith("You're checking one unit of a pack review."), prompt[:80])
        self.assertIn('- `context-packs/project/a.md`\n- `context-packs/project/b.md`\n', prompt)
        self.assertNotIn('c.md', prompt)
        self.assertNotIn('{', prompt.split('Read each one in full')[0])

    def test_gives_the_first_unit_the_instruction_file(self):
        prompt = self.prompt(0)['prompt']

        self.assertIn('- `AGENTS.md`\n', prompt)
        self.assertNotIn('a.md', prompt)

    def test_points_the_finder_at_the_git_server_for_the_diff_and_log(self):
        prompt = self.prompt(2)['prompt']

        self.assertIn("The diff is the git server's `diff` tool", prompt)
        self.assertIn("the log is the git server's `log` tool", prompt)

    def test_runs_the_finder_with_read_tools_and_the_git_server_and_no_subagents(self):
        args = shlex.split(self.prompt(0)['claude-args'])

        self.assertEqual(args[args.index('--tools') + 1], 'Read,Glob,Grep')
        self.assertEqual(args[args.index('--allowedTools') + 1], 'Read,Glob,Grep,mcp__git')
        servers = json.loads(args[args.index('--mcp-config') + 1])
        self.assertEqual(servers['mcpServers']['git']['args'][1:], ['--base', 'b' * 40, '--head', 'h' * 40])
        self.assertEqual(json.loads(args[args.index('--json-schema') + 1]),
                         json.loads((REVIEW / 'findings.schema.json').read_text()))
        self.assertIn('--restricted', args)
        self.assertNotIn('--plugin-dir', args)

    def test_refuses_a_unit_the_docs_dont_have(self):
        run = self.script('units', 'prompt', '--docs', 'docs.txt', '--unit', '3', '--base', 'b' * 40, '--head', 'h' * 40)

        self.assertEqual(run.returncode, 1)
        self.assertIn('3 units', run.stderr)
