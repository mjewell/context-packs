import re
from pathlib import Path
import unittest

from test_eval import BILLING, TESTING, EvalCase, case


class TriggerTests(EvalCase):
    """A doc's triggers.md, listing prompts that should and shouldn't make an agent read the doc."""

    def triggers(self, text, doc='testing'):
        self.publish({'pack.md': 'Prefer small PRs.\n', 'testing.md': TESTING, 'billing.md': BILLING,
                      f'.evals/{doc}/triggers.md': text})
        if not (self.repo / 'AGENTS.md').exists():
            self.add()
        else:
            self.sync('update')

    def work(self, result):
        return Path(re.search(r'^Reports and transcripts: (.*)$', result.stdout, re.MULTILINE).group(1))

    def test_each_trigger_scores_whether_the_doc_was_read_as_its_section_expects(self):
        self.triggers('## Reads\n\n- Writing tests for the parser\n\n'
                      '## Skips\n\n- Bump the version\n- Writing tests can wait, bump the version\n')

        result = self.eval('house-rules', 'testing')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertRegex(result.stdout, r'reads-1-writing-tests-for-the-parser +1\.00')
        self.assertRegex(result.stdout, r'skips-1-bump-the-version +1\.00')
        self.assertRegex(result.stdout, r'skips-2-writing-tests-can-wait-bump-the +0\.00')

    def test_triggers_run_only_with_the_doc(self):
        self.triggers('## Reads\n\n- Writing tests for the parser\n')

        result = self.eval('house-rules', 'testing')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.calls()), 1)
        self.assertNotIn('Without', result.stdout)

    def test_doc_with_cases_and_triggers_compares_only_the_cases(self):
        self.publish({**self.cases('testing', {'writes-test-first': case('Write the test first.')})})
        self.triggers('## Reads\n\n- Writing tests for the parser\n')

        result = self.eval('house-rules', 'testing')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertRegex(result.stdout, r'writes-test-first +0\.00 +1\.00 +\+1\.00')
        self.assertRegex(result.stdout, r'reads-1-writing-tests-for-the-parser +1\.00\n')
        self.assertEqual(len(self.calls()), 3)

    def test_indented_lines_continue_a_trigger(self):
        self.triggers('## Reads\n\n- Please help\n\n  ```\n  writing tests\n  ```\n')

        result = self.eval('house-rules', 'testing')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertRegex(result.stdout, r'reads-1-please-help +1\.00')
        prompt = (self.work(result) / 'triggers' / 'testing' / 'reads-1-please-help' / 'prompt.md').read_text()
        self.assertTrue(prompt.endswith('\nPlease help\n\n```\nwriting tests\n```\n'), prompt)

    def test_front_matter_goes_to_every_trigger_with_defaults_for_what_it_leaves_out(self):
        self.triggers('---\nmax_turns: 3\n---\n## Reads\n\n- Writing tests for the parser\n')

        result = self.eval('house-rules', 'testing')

        prompt = (self.work(result) / 'triggers' / 'testing' / 'reads-1-writing-tests-for-the-parser' /
                  'prompt.md').read_text()
        self.assertTrue(prompt.startswith('---\nmax_turns: 3\nallowed_tools: [Read, Glob, Grep]\n---\n'), prompt)

    def test_text_outside_a_trigger_stops_the_eval_and_names_its_line(self):
        self.triggers('## Reads\n\n- Writing tests for the parser\nnot indented\n')

        result = self.eval('house-rules', 'testing')

        self.assertEqual(result.returncode, 1)
        self.assertIn('.evals/testing/triggers.md:4', result.stderr)
        self.assertFalse(self.log.exists())

    def test_unknown_heading_stops_the_eval(self):
        self.triggers('## Should read\n\n- Writing tests for the parser\n')

        result = self.eval('house-rules', 'testing')

        self.assertEqual(result.returncode, 1)
        self.assertIn('.evals/testing/triggers.md:1', result.stderr)
        self.assertIn('## Reads', result.stderr)

    def test_trigger_before_any_heading_stops_the_eval(self):
        self.triggers('- Writing tests for the parser\n')

        result = self.eval('house-rules', 'testing')

        self.assertEqual(result.returncode, 1)
        self.assertIn('.evals/testing/triggers.md:1', result.stderr)

    def test_empty_trigger_stops_the_eval(self):
        self.triggers('## Reads\n\n-\n')

        result = self.eval('house-rules', 'testing')

        self.assertEqual(result.returncode, 1)
        self.assertIn('.evals/testing/triggers.md:3', result.stderr)

    def test_triggers_file_without_triggers_stops_the_eval(self):
        self.triggers('## Reads\n\n## Skips\n')

        result = self.eval('house-rules', 'testing')

        self.assertEqual(result.returncode, 1)
        self.assertIn('.evals/testing/triggers.md', result.stderr)

    def test_triggers_for_a_doc_the_pack_doesnt_have_stop_the_eval(self):
        self.triggers('## Reads\n\n- Deploying\n', doc='deploying')

        result = self.eval('house-rules')

        self.assertEqual(result.returncode, 1)
        self.assertIn('.evals/deploying', result.stderr)


class NestedTriggerTests(EvalCase):
    def test_doc_in_a_nested_pack_is_read_through_its_index(self):
        self.publish({'pack.md': 'Prefer small PRs.\n',
                      'typescript/pack.md': '---\nwhen: Editing TypeScript\n---\nPrefer unions.\n',
                      'typescript/types.md': '---\nwhen: Writing types\n---\nNo any.\n',
                      'typescript/.evals/types/triggers.md':
                          '## Reads\n\n- Editing TypeScript: writing types for the API\n\n'
                          '## Skips\n\n- Writing types, but not in TypeScript\n'})
        self.add()

        result = self.eval('house-rules', 'typescript/types')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertRegex(result.stdout, r'reads-1-editing-typescript-writing-types-for-the +1\.00')
        self.assertRegex(result.stdout, r'skips-1-writing-types-but-not-in-typescript +1\.00')


class SiblingTriggerTests(EvalCase):
    def test_doc_of_a_sibling_pack_is_read_where_the_run_has_it(self):
        self.publish({'pack.md': 'Prefer small PRs.\n', 'testing.md': TESTING,
                      '.evals/testing/triggers.md': '## Reads\n\n- Writing tests for the parser\n'})
        self.sync('add', 'house-rules', '../house-rules', '--path', 'context')

        result = self.eval('house-rules', 'testing')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertRegex(result.stdout, r'reads-1-writing-tests-for-the-parser +1\.00')


if __name__ == '__main__':
    unittest.main()
