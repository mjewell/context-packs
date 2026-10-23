import json
import os
from pathlib import Path
import sys

from test_cli import SyncCase, doc

FAKE = Path(__file__).resolve().parent / 'fake_claude.py'


class EvalCase(SyncCase):
    """A repo whose own docs have cases, run by `eval` against a fake claude on PATH."""

    def setUp(self):
        super().setUp()
        bin_dir = self.root / 'bin'
        bin_dir.mkdir()
        (bin_dir / 'claude').write_text(f'#!/bin/sh\nexec {sys.executable} {FAKE} "$@"\n')
        (bin_dir / 'claude').chmod(0o755)
        self.log = self.root / 'claude.log'
        self.env = {**self.env, 'PATH': f'{bin_dir}{os.pathsep}{self.env["PATH"]}', 'FAKE_CLAUDE_LOG': str(self.log)}
        self.write('context-packs/testing.md', doc('Writing tests', 'Use factories.\n'))
        self.sync()

    def cases(self, text, name='testing'):
        self.write(f'context-packs/.evals/{name}.md', text)


class EvalTests(EvalCase):
    def test_reads_prompt_whose_doc_gets_read_passes(self):
        self.cases('## Reads\n\n- Help me with writing tests for the parser\n')

        result = self.sync('eval')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('✓ testing.md  reads  Help me with writing tests for the parser', result.stdout)

    def test_reads_prompt_whose_doc_isnt_read_fails(self):
        self.cases('## Reads\n\n- Rename a variable in the parser\n')

        result = self.sync('eval')

        self.assertEqual(result.returncode, 1)
        self.assertIn('✗ testing.md  reads  Rename a variable in the parser', result.stdout)
        self.assertIn('read no docs', result.stdout)

    def test_skips_prompt_whose_doc_gets_read_fails(self):
        self.cases('## Skips\n\n- Help me with writing tests for the parser\n')

        result = self.sync('eval')

        self.assertEqual(result.returncode, 1)
        self.assertIn('✗ testing.md  skips  Help me with writing tests for the parser', result.stdout)
        self.assertIn('read: context-packs/testing.md', result.stdout)

    def test_lines_indented_under_an_item_continue_its_prompt(self):
        self.cases('## Reads\n\n- CI failed while writing tests\n  for the parser:\n\n  ```\n  FAIL parse\n  ```\n'
                   '- Help me with writing tests\n')

        result = self.sync('eval')

        self.assertEqual(result.returncode, 0, result.stderr)
        prompts = [json.loads(line)['args'][1] for line in self.log.read_text().splitlines()]
        self.assertIn('CI failed while writing tests\nfor the parser:\n\n```\nFAIL parse\n```', prompts)
        self.assertIn('✓ testing.md  reads  CI failed while writing tests\n', result.stdout)

    def test_stray_line_in_a_case_file_stops_naming_it(self):
        self.cases('## Reads\n\n- Help me with writing tests\nfor the parser\n')

        result = self.sync('eval')

        self.assertEqual(result.returncode, 1)
        self.assertIn('context-packs/.evals/testing.md:4', result.stderr)
        self.assertFalse(self.log.exists())

    def test_sessions_run_read_only_in_a_copy_without_git_or_the_cases(self):
        self.cases('## Reads\n\n- Help me with writing tests\n')

        result = self.sync('eval')

        self.assertEqual(result.returncode, 0, result.stderr)
        run = json.loads(self.log.read_text())
        self.assertFalse(run['cwd'].startswith(str(self.root)))
        self.assertIn('context-packs/testing.md', run['files'])
        self.assertFalse([f for f in run['files'] if f.startswith('.git') or '.evals' in f])
        for flags in (['--output-format', 'stream-json'], ['--setting-sources', 'project'], ['--tools', 'Read,Glob,Grep'],
                      ['--allowedTools', 'Read,Glob,Grep'], ['--strict-mcp-config']):
            self.assertIn(' '.join(flags), ' '.join(run['args']))

    def test_runs_repeats_each_prompt_and_counts_the_passes(self):
        self.cases('## Reads\n\n- Help me with writing tests\n')

        result = self.sync('eval', '--runs', '3')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.log.read_text().splitlines()), 3)
        self.assertIn('✓ testing.md  reads  3/3  Help me with writing tests', result.stdout)

    def test_naming_docs_runs_only_their_cases(self):
        self.write('context-packs/releasing.md', doc('Releasing a version'))
        self.sync()
        self.cases('## Reads\n\n- Help me with writing tests\n')
        self.cases('## Reads\n\n- Help me with releasing a version\n', name='releasing')

        result = self.sync('eval', 'releasing.md')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('✓ releasing.md  reads  Help me with releasing a version\n', result.stdout)
        self.assertNotIn('testing.md', result.stdout)

    def test_repo_without_cases_says_so(self):
        result = self.sync('eval')

        self.assertEqual(result.returncode, 1)
        self.assertIn('no doc has cases', result.stderr)
        self.assertFalse(self.log.exists())

    def test_pack_read_in_place_runs_its_docs_cases(self):
        self.write('rules/pack.md', 'Prefer small PRs.\n')
        self.write('rules/deploying.md', doc('Deploying to production'))
        self.write('rules/.evals/deploying.md', '## Reads\n\n- Help me with deploying to production\n')
        self.write('context-packs/core/pack.md', '---\npath: rules\n---\n')
        self.sync()

        result = self.sync('eval', 'core/deploying.md')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('✓ core/deploying.md  reads  Help me with deploying to production\n', result.stdout)

    def test_stale_block_stops_before_any_session(self):
        self.cases('## Reads\n\n- Help me with writing tests\n')
        self.write('context-packs/testing.md', doc('Writing or changing tests'))

        result = self.sync('eval')

        self.assertEqual(result.returncode, 1)
        self.assertIn('stale', result.stderr)
        self.assertFalse(self.log.exists())


    def test_sessions_use_sonnet_unless_told_otherwise(self):
        self.cases('## Reads\n\n- Help me with writing tests\n')

        self.sync('eval')
        self.sync('eval', '--model', 'haiku')

        models = [run['args'][run['args'].index('--model') + 1] for run in map(json.loads, self.log.read_text().splitlines())]
        self.assertEqual(models, ['sonnet', 'haiku'])

    def test_session_ends_once_it_reads_the_doc(self):
        self.cases('## Reads\n\n- Help me with writing tests\n\n## Skips\n\n- Writing tests again, please\n')
        self.env['FAKE_CLAUDE_SLEEP'] = '60'

        result = self.sync('eval')

        self.assertEqual(result.returncode, 1)
        self.assertIn('✓ testing.md  reads  Help me with writing tests', result.stdout)
        self.assertIn('✗ testing.md  skips  Writing tests again, please', result.stdout)

    def test_output_says_what_runs_then_how_it_went(self):
        self.cases('## Reads\n\n- Help me with writing tests\n- Writing tests again, please\n')

        result = self.sync('eval', '--runs', '2')

        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.splitlines()
        self.assertEqual(lines[0], 'Running 2 prompts for 1 doc, 2 times each, in a copy of the repo, on sonnet…')
        self.assertEqual(lines[-1], '2 passed')

class FixtureTests(EvalCase):
    """A fixture/ folder beside a doc's cases: they run in a copy of it, with this repo's packs synced into it."""

    def setUp(self):
        super().setUp()
        self.write('context-packs/.evals/fixture/src/parse.ts', 'export const parse = () => 1;\n')

    def runs(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def test_cases_beside_a_fixture_run_in_it_with_the_repos_packs(self):
        self.cases('## Reads\n\n- Help me with writing tests\n')

        result = self.sync('eval')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('✓ testing.md  reads  Help me with writing tests', result.stdout)
        files = self.runs()[0]['files']
        self.assertIn('src/parse.ts', files)
        self.assertIn('context-packs/testing.md', files)
        self.assertFalse([f for f in files if '.evals' in f])
        self.assertFalse((self.packs / '.evals' / 'fixture' / 'AGENTS.md').exists())

    def test_cases_without_a_fixture_still_run_in_the_repo(self):
        self.cases('## Reads\n\n- Help me with writing tests\n')
        self.write('context-packs/ops/releasing.md', doc('Releasing a version'))
        self.write('context-packs/ops/.evals/releasing.md', '## Reads\n\n- Help me with releasing a version\n')
        self.sync()

        result = self.sync('eval')

        self.assertEqual(result.returncode, 0, result.stderr)
        by_prompt = {run['args'][1]: run['files'] for run in self.runs()}
        self.assertIn('src/parse.ts', by_prompt['Help me with writing tests'])
        self.assertNotIn('src/parse.ts', by_prompt['Help me with releasing a version'])

    def test_pack_read_in_place_points_at_this_repo_from_its_fixture(self):
        self.write('rules/pack.md', 'Prefer small PRs.\n')
        self.write('rules/deploying.md', doc('Deploying to production'))
        self.write('rules/.evals/deploying.md', '## Reads\n\n- Help me with deploying to production\n')
        self.write('rules/.evals/fixture/src/app.ts', 'export {};\n')
        self.write('context-packs/core/pack.md', '---\npath: rules\n---\n')
        self.sync()

        result = self.sync('eval', 'core/deploying.md')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('✓ core/deploying.md  reads  Help me with deploying to production\n', result.stdout)
        files = self.runs()[0]['files']
        self.assertIn('src/app.ts', files)
        self.assertNotIn('rules/deploying.md', files)

    def test_fixture_beside_a_packs_cases_gets_only_that_pack(self):
        self.write('rules/pack.md', 'Prefer small PRs.\n')
        self.write('rules/deploying.md', doc('Deploying to production'))
        self.write('rules/.evals/deploying.md', '## Reads\n\n- Help me with deploying to production\n')
        self.write('rules/.evals/fixture/src/app.ts', 'export {};\n')
        self.write('context-packs/core/pack.md', '---\npath: rules\n---\n')
        self.sync()

        result = self.sync('eval', 'core/deploying.md')

        self.assertEqual(result.returncode, 0, result.stderr)
        files = self.runs()[0]['files']
        self.assertIn('context-packs/core/pack.md', files)
        self.assertNotIn('context-packs/testing.md', files)

    def test_fixture_beside_the_repos_own_cases_gets_everything_the_repo_installs(self):
        self.cases('## Reads\n\n- Help me with writing tests\n')
        self.write('rules/pack.md', 'Prefer small PRs.\n')
        self.write('rules/deploying.md', doc('Deploying to production'))
        self.write('context-packs/core/pack.md', '---\npath: rules\n---\n')
        self.sync()

        result = self.sync('eval')

        self.assertEqual(result.returncode, 0, result.stderr)
        files = self.runs()[0]['files']
        self.assertIn('context-packs/testing.md', files)
        self.assertIn('context-packs/core/pack.md', files)
        self.assertNotIn('rules/deploying.md', files)

    def test_linked_fixture_is_copied_like_a_folder(self):
        self.write('rules/pack.md', 'Prefer small PRs.\n')
        self.write('rules/deploying.md', doc('Deploying to production'))
        self.write('rules/.evals/deploying.md', '## Reads\n\n- Help me with deploying to production\n')
        (self.repo / 'rules' / '.evals' / 'fixture').symlink_to('../../context-packs/.evals/fixture')
        self.write('context-packs/core/pack.md', '---\npath: rules\n---\n')
        self.sync()

        result = self.sync('eval', 'core/deploying.md')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('src/parse.ts', self.runs()[0]['files'])

    def test_fixture_with_its_own_context_packs_stops(self):
        self.cases('## Reads\n\n- Help me with writing tests\n')
        self.write('context-packs/.evals/fixture/context-packs/pack.md', 'Its own rules.\n')

        result = self.sync('eval')

        self.assertEqual(result.returncode, 1)
        self.assertIn('has a context-packs/ folder of its own', result.stderr)
        self.assertFalse(self.log.exists())
