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
        self.assertNotIn('also read', result.stdout)

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

    def test_prompt_that_passes_lists_the_other_docs_its_session_read(self):
        self.write('context-packs/releasing.md', doc('Releasing a version'))
        self.sync()
        self.cases('## Reads\n\n- Help me with writing tests before releasing a version\n')
        self.cases('## Skips\n\n- Help me with writing tests\n', name='releasing')

        result = self.sync('eval')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('✓ testing.md  reads  Help me with writing tests before releasing a version\n'
                      '    also read: context-packs/releasing.md\n', result.stdout)
        self.assertIn('✓ releasing.md  skips  Help me with writing tests\n'
                      '    also read: context-packs/testing.md\n', result.stdout)

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
        for flags in (['--output-format', 'stream-json'], ['--setting-sources', 'project'],
                      ['--tools', 'Read,Glob,Grep'], ['--allowedTools', 'Read,Glob,Grep'], ['--strict-mcp-config']):
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
        self.assertIn('no pack has eval prompts', result.stderr)
        self.assertFalse(self.log.exists())

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

        runs = map(json.loads, self.log.read_text().splitlines())
        models = [run['args'][run['args'].index('--model') + 1] for run in runs]
        self.assertEqual(models, ['sonnet', 'haiku'])

    def test_session_ends_once_it_reads_the_doc(self):
        self.cases('## Reads\n\n- Help me with writing tests\n\n## Skips\n\n- Writing tests again, please\n')
        self.env['FAKE_CLAUDE_SLEEP'] = '60'

        result = self.sync('eval')

        self.assertEqual(result.returncode, 1)
        self.assertIn('✓ testing.md  reads  Help me with writing tests', result.stdout)
        self.assertIn('✗ testing.md  skips  Writing tests again, please', result.stdout)

    def test_session_that_errors_shows_its_error_instead_of_passing(self):
        self.cases('## Skips\n\n- Rename a variable in the parser\n')
        self.env['FAKE_CLAUDE_ERROR'] = 'There\'s an issue with the selected model (sonnet).'

        result = self.sync('eval')

        self.assertEqual(result.returncode, 1)
        self.assertIn('! testing.md  skips  Rename a variable in the parser\n'
                      '    error: There\'s an issue with the selected model (sonnet).\n', result.stdout)
        self.assertEqual(result.stdout.splitlines()[-1], '1 of 1 errored')

    def test_runs_that_error_alike_show_their_error_once_and_count_no_passes(self):
        self.cases('## Skips\n\n- Rename a variable in the parser\n')
        self.env['FAKE_CLAUDE_ERROR'] = 'Not logged in.'

        result = self.sync('eval', '--runs', '2')

        self.assertIn('! testing.md  skips  0/2  Rename a variable in the parser\n'
                      '    error: Not logged in.\n1 of 1 errored\n', result.stdout)

    def test_session_that_ends_without_a_result_shows_what_claude_printed(self):
        self.cases('## Skips\n\n- Rename a variable in the parser\n')
        self.env['FAKE_CLAUDE_CRASH'] = 'TypeError: undefined is not a function'

        result = self.sync('eval')

        self.assertEqual(result.returncode, 1)
        self.assertIn('! testing.md  skips  Rename a variable in the parser\n'
                      '    error: TypeError: undefined is not a function\n', result.stdout)

    def test_session_that_runs_out_of_turns_just_ends(self):
        self.cases('## Skips\n\n- Rename a variable in the parser\n')
        self.env['FAKE_CLAUDE_MAX_TURNS'] = '1'

        result = self.sync('eval')

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn('✓ testing.md  skips  Rename a variable in the parser', result.stdout)

    def test_json_prints_only_one_document_of_each_prompt_and_its_runs(self):
        self.write('context-packs/releasing.md', doc('Releasing a version'))
        self.sync()
        self.cases('## Reads\n\n- Help me with writing tests before releasing a version\n\n'
                   '## Skips\n\n- Rename a variable\n')

        result = self.sync('eval', '--json', '--runs', '2')

        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output['model'], 'sonnet')
        self.assertEqual(output['runs'], 2)
        reads, skips = output['cases']
        self.assertEqual({key: reads[key] for key in ('doc', 'expect', 'prompt', 'outcome', 'passes')},
                         {'doc': 'testing.md', 'expect': 'reads',
                          'prompt': 'Help me with writing tests before releasing a version',
                          'outcome': 'passed', 'passes': 2})
        self.assertEqual([run['read'] for run in reads['runs']],
                         [['context-packs/releasing.md', 'context-packs/testing.md']] * 2)
        self.assertEqual([run['error'] for run in reads['runs']], [None, None])
        self.assertEqual((skips['prompt'], skips['outcome']), ('Rename a variable', 'passed'))

    def test_json_gives_each_runs_time_and_its_cost_when_it_ran_to_the_end(self):
        self.cases('## Reads\n\n- Help me with writing tests\n\n## Skips\n\n- Rename a variable\n')

        result = self.sync('eval', '--json')

        (stopped,), (finished,) = (case['runs'] for case in json.loads(result.stdout)['cases'])
        self.assertEqual((stopped['cost_usd'], finished['cost_usd']), (None, 0.0123))
        self.assertIsInstance(stopped['duration_ms'], int)
        self.assertIsInstance(finished['duration_ms'], int)

    def test_json_gives_a_sessions_error_and_still_exits_1(self):
        self.cases('## Skips\n\n- Rename a variable\n')
        self.env['FAKE_CLAUDE_ERROR'] = 'Not logged in.'

        result = self.sync('eval', '--json')

        self.assertEqual(result.returncode, 1)
        (case,) = json.loads(result.stdout)['cases']
        self.assertEqual((case['outcome'], case['runs'][0]['error']), ('errored', 'Not logged in.'))

    def test_output_says_what_runs_then_how_it_went(self):
        self.cases('## Reads\n\n- Help me with writing tests\n- Writing tests again, please\n')

        result = self.sync('eval', '--runs', '2')

        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.splitlines()
        self.assertEqual(lines[0], 'Running 2 prompts for 1 doc, 2 times each, in a copy of the repo, on sonnet…')
        self.assertEqual(lines[-1], '2 passed')

class PackTests(EvalCase):
    """A pack's .evals/ at its root: its prompts run with that pack installed alone, plus everything inside it. For
    context-packs/, the pack at the top, that's the whole repo."""

    def setUp(self):
        super().setUp()
        self.write('rules/pack.md', 'Prefer small PRs.\n')
        self.write('rules/deploying.md', doc('Deploying to production'))
        self.write('rules/.evals/deploying.md', '## Reads\n\n- Help me with deploying to production\n')

    def install(self):
        self.write('context-packs/core/pack.md', '---\npath: rules\n---\n')
        self.sync()

    def runs(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def test_installed_packs_prompts_run_with_only_that_pack(self):
        self.install()

        result = self.sync('eval', 'deploying.md')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('✓ rules/deploying.md  reads  Help me with deploying to production\n', result.stdout)
        files = self.runs()[0]['files']
        self.assertIn('context-packs/rules/pack.md', files)
        self.assertNotIn('context-packs/testing.md', files)

    def test_pack_without_a_fixture_runs_in_an_empty_folder(self):
        self.install()

        self.sync('eval', 'deploying.md')

        self.assertEqual(sorted(self.runs()[0]['files']), ['AGENTS.md', 'CLAUDE.md', 'context-packs',
                                                           'context-packs/rules', 'context-packs/rules/pack.md'])

    def test_pack_with_a_fixture_runs_in_it_with_only_that_pack(self):
        self.write('rules/.evals/fixture/src/app.ts', 'export {};\n')
        self.install()

        result = self.sync('eval', 'deploying.md')

        self.assertEqual(result.returncode, 0, result.stderr)
        files = self.runs()[0]['files']
        self.assertIn('src/app.ts', files)
        self.assertNotIn('context-packs/testing.md', files)
        self.assertFalse([f for f in files if '.evals' in f])

    def test_pack_not_installed_runs_the_same_with_pack(self):
        result = self.sync('eval', '--pack', 'rules')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('✓ rules/deploying.md  reads  Help me with deploying to production\n', result.stdout)

    def test_top_packs_prompts_test_an_installed_packs_doc_within_the_whole_repo(self):
        self.install()
        self.cases('## Reads\n\n- Help me with deploying to production\n', name='core/deploying')

        result = self.sync('eval', 'core/deploying.md')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('✓ core/deploying.md  reads  Help me with deploying to production\n', result.stdout)
        files = self.runs()[0]['files']
        self.assertIn('context-packs/testing.md', files)
        self.assertIn('context-packs/core/pack.md', files)

    def test_top_packs_fixture_gets_all_of_context_packs(self):
        self.install()
        self.cases('## Reads\n\n- Help me with writing tests\n')
        self.write('context-packs/.evals/fixture/src/parse.ts', 'export const parse = () => 1;\n')

        result = self.sync('eval', 'testing.md')

        self.assertEqual(result.returncode, 0, result.stderr)
        files = self.runs()[0]['files']
        self.assertIn('src/parse.ts', files)
        self.assertIn('context-packs/testing.md', files)
        self.assertIn('context-packs/core/pack.md', files)

    def test_nested_packs_prompts_run_with_only_that_nested_pack(self):
        self.write('context-packs/server/pack.md', doc('Editing the server'))
        self.write('context-packs/server/database.md', doc('Changing the database'))
        self.write('context-packs/server/.evals/database.md',
                   '## Reads\n\n- Editing the server: help me with changing the database\n')
        self.sync()

        result = self.sync('eval', 'database.md')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('context-packs/server/database.md  reads', result.stdout)
        self.assertNotIn('context-packs/testing.md', self.runs()[0]['files'])

    def test_case_file_naming_no_doc_in_its_pack_stops(self):
        self.write('rules/.evals/releasing.md', '## Reads\n\n- Help me with releasing\n')
        self.install()

        result = self.sync('eval')

        self.assertEqual(result.returncode, 1)
        self.assertIn('rules/.evals/releasing.md names no doc in rules', result.stderr)
        self.assertFalse(self.log.exists())

    def test_linked_fixture_is_copied_like_a_folder(self):
        self.write('shared/src/parse.ts', 'export const parse = () => 1;\n')
        (self.repo / 'rules' / '.evals' / 'fixture').symlink_to('../../shared')
        self.install()

        result = self.sync('eval', 'deploying.md')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('src/parse.ts', self.runs()[0]['files'])

    def test_fixture_with_its_own_context_packs_stops(self):
        self.write('rules/.evals/fixture/context-packs/pack.md', 'Its own rules.\n')
        self.install()

        result = self.sync('eval')

        self.assertEqual(result.returncode, 1)
        self.assertIn('has a context-packs/ folder of its own', result.stderr)
        self.assertFalse(self.log.exists())
