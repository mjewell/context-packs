import json
import os
from pathlib import Path
import pty
import re
import select
import shutil
import subprocess
import sys
import unittest

from test_cli import CLI, SyncCase

FAKE_CLAUDE = Path(__file__).resolve().parent / 'fake_claude.py'
TESTING = '---\nwhen: Writing tests\n---\nWrite the test first.\n'
BILLING = '---\nwhen: Editing billing\n---\nCharge once.\n'


def case(pattern, name=None):
    """A case's files: a prompt, and a grader passing when pattern is in what the run saw."""
    files = {'prompt.md': '---\nmax_turns: 5\n---\n\nAdd a feature.\n',
             'graders/rule.md': f'---\ntype: regex\npattern: {pattern}\n---\n'}
    if name:
        files['case.yaml'] = f'schema_version: "1.0"\nname: {name}\n'
    return files


class EvalCase(SyncCase):
    """A repo with a pack installed whose .evals folder holds cases, run against a stand-in for claude."""

    def setUp(self):
        super().setUp()
        bin_dir = self.root / 'bin'
        bin_dir.mkdir()
        (bin_dir / 'claude').write_text(f'#!/bin/sh\nexec "{sys.executable}" "{FAKE_CLAUDE}" "$@"\n')
        (bin_dir / 'claude').chmod(0o755)
        self.log = self.root / 'claude.log'
        self.env = {**self.env, 'PATH': f'{bin_dir}{os.pathsep}{os.environ["PATH"]}',
                    'FAKE_CLAUDE_LOG': str(self.log), 'TMPDIR': str(self.root)}

    def cases(self, doc, cases):
        """Files for the pack: each case's files in the folder .evals/<doc>/<case>/."""
        return {f'.evals/{doc}/{name}/{path}': text for name, files in cases.items() for path, text in files.items()}

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def eval(self, *args):
        return self.sync('eval', *args)


class EvalTests(EvalCase):
    def setUp(self):
        super().setUp()
        self.publish({'pack.md': 'Prefer small PRs.\n', 'testing.md': TESTING, 'billing.md': BILLING,
                      **self.cases('testing', {'writes-test-first': case('Write the test first.'),
                                               'keeps-prs-small': case('Prefer small PRs.')})})
        self.add()

    def test_doc_left_out_lowers_the_score_of_cases_that_rely_on_it(self):
        result = self.eval('house-rules', 'testing')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertRegex(result.stdout, r'house-rules/testing\.md')
        self.assertRegex(result.stdout, r'writes-test-first +0\.00 +1\.00 +\+1\.00')

    def test_rest_of_the_pack_and_instructions_stay_when_the_doc_is_left_out(self):
        (self.repo / 'AGENTS.md').write_text('# Our repo\n\nUse pnpm.\n\n' + (self.repo / 'AGENTS.md').read_text())
        self.publish(self.cases('billing', {'charges-once': case('Charge once.'),
                                            'uses-pnpm': case('Use pnpm.')}))
        self.sync('update')

        result = self.eval('house-rules', 'testing')
        billing = self.eval('house-rules', 'billing')

        self.assertRegex(result.stdout, r'keeps-prs-small +1\.00 +1\.00 +\+0\.00')
        self.assertRegex(billing.stdout, r'charges-once +0\.00 +1\.00 +\+1\.00')
        self.assertRegex(billing.stdout, r'uses-pnpm +1\.00 +1\.00 +\+0\.00')

    def test_each_run_passes_claude_the_options_after_a_double_dash(self):
        result = self.eval('house-rules', 'testing', '--', '--runs', '1', '--model', 'haiku')

        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls()
        self.assertEqual(len(calls), 4)
        for call in calls:
            self.assertEqual(call[:2], ['plugin', 'eval'])
            self.assertIn('--ablation', call)
            self.assertEqual(call[call.index('--ablation') + 1], 'none')
            self.assertEqual(call[-4:], ['--runs', '1', '--model', 'haiku'])

    def test_runs_on_haiku_unless_the_options_name_a_model(self):
        default = self.eval('house-rules', 'testing')
        default_calls = self.calls()
        self.log.unlink()
        chosen = self.eval('house-rules', 'testing', '--', '--model', 'sonnet')

        self.assertEqual(default.returncode, 0, default.stderr)
        self.assertIn('on haiku', default.stdout)
        for call in default_calls:
            self.assertEqual(call[call.index('--model') + 1], 'haiku')
        self.assertIn('on sonnet', chosen.stdout)
        for call in self.calls():
            self.assertEqual(call.count('--model'), 1)
            self.assertEqual(call[call.index('--model') + 1], 'sonnet')

    def test_concurrency_sizes_the_pool_and_isnt_passed_on(self):
        result = self.eval('house-rules', 'testing', '--', '-j', '2')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('2 at a time', result.stdout)
        for call in self.calls():
            self.assertNotIn('-j', call)
            self.assertNotIn('--concurrency', call)

    def test_plan_lists_each_case_before_the_results(self):
        result = self.eval('house-rules', 'testing')

        self.assertEqual(result.returncode, 0, result.stderr)
        plan = result.stdout.index('house-rules: 4 cases on haiku, 4 at a time')
        for line in (r'\[ \] testing\.md +writes-test-first +without the doc',
                     r'\[ \] testing\.md +writes-test-first +with the doc',
                     r'\[ \] testing\.md +keeps-prs-small +with the doc'):
            self.assertLess(plan, re.search(line, result.stdout).start())
        self.assertLess(plan, result.stdout.index('house-rules/testing.md\n'))

    def test_each_finished_case_prints_a_line(self):
        result = self.eval('house-rules', 'testing')

        self.assertRegex(result.stdout, r'\[x\] testing\.md +writes-test-first +without the doc +0\.00')
        self.assertRegex(result.stdout, r'\[x\] testing\.md +writes-test-first +with the doc +1\.00')

    def test_on_a_terminal_each_case_shows_running_then_done_in_place(self):
        main, secondary = pty.openpty()
        process = subprocess.Popen([sys.executable, str(CLI), 'eval', 'house-rules', 'testing'], cwd=self.repo,
                                   env=self.env, stdin=secondary, stdout=secondary, stderr=secondary)
        os.close(secondary)
        output, pressed = b'', False
        while select.select([main], [], [], 30)[0]:
            try:
                chunk = os.read(main, 4096)
            except OSError:
                break
            if not chunk:
                break
            output += chunk
            if not pressed and b'Starting in' in output:
                os.write(main, b'\n')
                pressed = True
        os.close(main)
        text = output.decode()

        self.assertEqual(process.wait(timeout=30), 0, text)
        self.assertRegex(text, r'\x1b\[\d+A\r\x1b\[K  \[-\] testing\.md +writes-test-first +with the doc')
        self.assertRegex(text, r'\x1b\[\d+A\r\x1b\[K  \[x\] testing\.md +writes-test-first +with the doc +1\.00')

    def test_without_a_doc_every_doc_with_cases_is_evaluated(self):
        self.publish(self.cases('billing', {'charges-once': case('Charge once.')}))
        self.sync('update')

        result = self.eval('house-rules')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertRegex(result.stdout, r'charges-once +0\.00 +1\.00')
        self.assertRegex(result.stdout, r'writes-test-first +0\.00 +1\.00')
        self.assertEqual(len(self.calls()), 6)

    def test_doc_without_cases_stops_and_names_the_docs_that_have_them(self):
        result = self.eval('house-rules', 'billing')

        self.assertEqual(result.returncode, 1)
        self.assertIn('billing', result.stderr)
        self.assertIn('testing', result.stderr)
        self.assertFalse(self.log.exists())

    def test_pack_not_installed_stops(self):
        result = self.eval('acme')

        self.assertEqual(result.returncode, 1)
        self.assertIn('acme', result.stderr)

    def test_cases_for_a_doc_the_pack_doesnt_have_stop_the_eval(self):
        self.publish(self.cases('deploying', {'ships-it': case('Ship it.')}))
        self.sync('update')

        result = self.eval('house-rules')

        self.assertEqual(result.returncode, 1)
        self.assertIn('.evals/deploying', result.stderr)
        self.assertFalse(self.log.exists())

    def test_two_cases_of_a_doc_with_one_name_stop_the_eval(self):
        self.publish(self.cases('billing', {'a': case('Charge once.', name='same'),
                                            'b': case('Charge once.', name='same')}))
        self.sync('update')

        result = self.eval('house-rules', 'billing')

        self.assertEqual(result.returncode, 1)
        self.assertIn('same', result.stderr)

    def test_claude_failing_stops_the_eval(self):
        self.env['FAKE_CLAUDE_FAIL'] = '1'

        result = self.eval('house-rules', 'testing')

        self.assertEqual(result.returncode, 1)
        self.assertIn('claude plugin eval', result.stderr)
        self.assertIn('something went wrong', result.stderr)

    def test_options_after_a_double_dash_belong_only_to_eval(self):
        result = self.sync('list', '--', '--runs', '1')

        self.assertEqual(result.returncode, 2)


class NestedEvalTests(EvalCase):
    def test_nested_packs_cases_sit_in_its_own_evals_folder(self):
        self.publish({'pack.md': 'Prefer small PRs.\n',
                      'typescript/pack.md': '---\nwhen: Editing TypeScript\n---\nPrefer unions.\n',
                      'typescript/types.md': '---\nwhen: Writing types\n---\nNo any.\n',
                      'typescript/.evals/types/avoids-any/prompt.md': case('No any.')['prompt.md'],
                      'typescript/.evals/types/avoids-any/graders/rule.md': case('No any.')['graders/rule.md']})
        self.add()

        result = self.eval('house-rules', 'typescript/types')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertRegex(result.stdout, r'avoids-any +0\.00 +1\.00')


class LocalPackEvalTests(EvalCase):
    def test_sibling_pack_is_evaluated_from_its_working_tree(self):
        self.publish({'pack.md': 'Prefer small PRs.\n', 'testing.md': TESTING,
                      **self.cases('testing', {'writes-test-first': case('Write the test first, always.')})})
        self.sync('add', 'house-rules', '../house-rules', '--path', 'context')
        (self.source / 'context' / 'testing.md').write_text(TESTING.replace('first.', 'first, always.'))

        result = self.eval('house-rules', 'testing')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertRegex(result.stdout, r'writes-test-first +0\.00 +1\.00')

    def test_pack_in_the_repo_itself_keeps_its_docs_where_they_are(self):
        docs = self.repo / 'docs' / 'agents' / 'project'
        docs.mkdir(parents=True)
        (docs / 'deploying.md').write_text('---\nwhen: Deploying\n---\nShip it.\n')
        files = {**case('docs/agents/project/deploying.md'),
                 'graders/content.md': '---\ntype: regex\npattern: Ship it.\n---\n'}
        for path, text in files.items():
            (docs / '.evals' / 'deploying' / 'ships-it' / path).parent.mkdir(parents=True, exist_ok=True)
            (docs / '.evals' / 'deploying' / 'ships-it' / path).write_text(text)
        self.sync('add', 'project', '.', '--path', 'docs/agents/project')

        result = self.eval('project', 'deploying')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertRegex(result.stdout, r'ships-it +0\.00 +1\.00')



class RepoEvalsTests(EvalCase):
    """The tests on this repo's own project docs, which double as the example of the format."""

    def test_project_docs_tests_run(self):
        shutil.copytree(Path(__file__).resolve().parents[1] / 'docs' / 'agents' / 'project',
                        self.repo / 'docs' / 'agents' / 'project', ignore=shutil.ignore_patterns('__pycache__'))
        self.sync('add', 'project', '.', '--path', 'docs/agents/project')

        result = self.eval('project')

        self.assertEqual(result.returncode, 0, result.stderr)
        for name in ('stops-npm-tagging', 'reads-1-release-0-4-0-to-npm', 'skips-1-fix-the-typo-teh-in-readme',
                     'reads-1-should-a-repo-be-able-to', 'skips-2-rename-the-sets-function-in-src'):
            self.assertIn(name, result.stdout)

if __name__ == '__main__':
    unittest.main()
