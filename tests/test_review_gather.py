import json
import os
import sys

from review_case import REVIEW, ReviewCase

FAKE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fake_review_claude.py')
FINDING = {'kind': 'deviates', 'inline': True, 'headline': 'A game number in sim code',
           'rules': [{'file': 'AGENTS.md', 'quote': 'Game numbers live in content.', 'routed': True}],
           'spots': [{'path': 'src/sim/slow.ts', 'line': 3, 'follows': False}], 'deliberate': [], 'exemplars': [],
           'take': 'Move it to content.'}
NEW = {'action': 'new', 'path': 'src/sim/slow.ts', 'line': 3, 'body': 'Deviates from a rule.'}


def result(**fields):
    return json.dumps({'type': 'result', 'subtype': 'success', 'is_error': False, 'result': '',
                       'total_cost_usd': 1.25, **fields})


class GatherTests(ReviewCase):
    """Running the pack-review skill headless over a PR, and keeping what it found."""

    def setUp(self):
        super().setUp()
        bin_dir = self.root / 'bin'
        bin_dir.mkdir()
        (bin_dir / 'claude').write_text(f'#!/bin/sh\nexec {sys.executable} {FAKE} "$@"\n')
        (bin_dir / 'claude').chmod(0o755)
        self.log = self.root / 'claude.log'
        self.inputs = self.root / 'inputs'
        self.inputs.mkdir()
        (self.inputs / 'comments.json').write_text('{}')
        self.env = {**self.env, 'PATH': f'{bin_dir}{os.pathsep}{self.env["PATH"]}',
                    'FAKE_CLAUDE_LOG': str(self.log),
                    'FAKE_CLAUDE_RESULT': result(structured_output={'findings': [FINDING], 'threads': [NEW]})}

    def gather(self, *extra):
        return self.script('gather', '--base', 'b' * 40, '--head', 'h' * 40, '--comments',
                           self.inputs / 'comments.json', '--out', 'findings.json', *extra)

    def args(self):
        [run] = [json.loads(line) for line in self.log.read_text().splitlines()]
        return run['args']

    def flag(self, name):
        args = self.args()
        return args[args.index(name) + 1]

    def test_writes_what_the_agent_found_with_the_commits_it_reviewed(self):
        result = self.gather()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads((self.root / 'findings.json').read_text()),
                         {'base': 'b' * 40, 'head': 'h' * 40, 'findings': [FINDING], 'threads': [NEW]})
        self.assertIn('$1.25', result.stdout)

    def test_runs_the_skill_in_ci_mode_on_the_range_and_comments(self):
        self.gather()

        self.assertEqual(self.flag('-p'), f'/context-packs:pack-review ci {"b" * 40}...{"h" * 40} '
                                          f'{self.inputs / "comments.json"}')
        self.assertEqual(self.flag('--plugin-dir'), str(REVIEW.parent))
        self.assertEqual(self.flag('--add-dir'), str(self.inputs))
        self.assertEqual(json.loads(self.flag('--json-schema')),
                         json.loads((REVIEW / 'findings.schema.json').read_text()))

    def test_gives_the_agent_tools_that_only_read_and_no_shell_but_git(self):
        self.gather()

        self.assertEqual(self.flag('--tools'), 'Read,Glob,Grep,Bash,Agent')
        self.assertEqual(self.flag('--allowedTools'),
                         'Read,Glob,Grep,Agent,Bash(git diff:*),Bash(git log:*),Bash(git show:*)')
        self.assertIn('--bare', self.args())
        self.assertIn('--restricted', self.args())
        self.assertIn('--strict-mcp-config', self.args())

    def test_passes_a_model_when_given_one(self):
        self.gather('--model', 'opus')

        self.assertEqual(self.flag('--model'), 'opus')

    def test_stops_when_the_agent_fails(self):
        self.env['FAKE_CLAUDE_RESULT'] = result(is_error=True, subtype='error_max_budget_usd',
                                                result='Spent the budget.')

        result_ = self.gather()

        self.assertEqual(result_.returncode, 1)
        self.assertIn('error_max_budget_usd', result_.stderr)
        self.assertIn('Spent the budget.', result_.stderr)
        self.assertFalse((self.root / 'findings.json').exists())

    def test_stops_when_the_agent_returns_no_findings_object(self):
        self.env['FAKE_CLAUDE_RESULT'] = result(result='Here are my findings: none.')

        result_ = self.gather()

        self.assertEqual(result_.returncode, 1)
        self.assertIn('returned no findings', result_.stderr)

    def test_stops_when_claude_crashes(self):
        self.env['FAKE_CLAUDE_CRASH'] = '3'

        result_ = self.gather()

        self.assertEqual(result_.returncode, 1)
        self.assertIn('exited with code 3', result_.stderr)
        self.assertIn('something broke', result_.stderr)
