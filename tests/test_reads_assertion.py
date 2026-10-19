import json
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
READS = ROOT / 'evals' / 'reads.js'
WORKSPACE = '/tmp/promptfoo-workspace-x/workspace'


def grade(read, **variables):
    """reads.js's result for a run that read the files in read, given as paths in the run's workspace, with the case's
    variables, passed the way promptfoo passes a javascript assertion its context."""
    calls = [{'name': 'Read', 'input': {'file_path': f'{WORKSPACE}/{path}'}} for path in read]
    context = {'vars': variables, 'providerResponse': {'metadata': {'toolCalls': calls}}}
    script = f'console.log(JSON.stringify(require({json.dumps(str(READS))})("", {json.dumps(context)})))'
    result = subprocess.run(['node', '-e', script], text=True, capture_output=True, timeout=30)
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)


@unittest.skipUnless(shutil.which('node'), 'promptfoo runs the assertion under node')
class ReadsAssertionTests(unittest.TestCase):
    """evals/reads.js, the promptfoo assertion that checks which context docs an agent's run read."""

    def test_run_that_read_the_expected_doc_passes(self):
        result = grade(['context-packs/gen/core/testing.md'], reads='testing.md')

        self.assertTrue(result['pass'], result['reason'])

    def test_run_that_missed_the_expected_doc_fails_naming_it(self):
        result = grade(['src/dates.ts'], reads='testing.md')

        self.assertFalse(result['pass'])
        self.assertIn('missing: testing.md', result['reason'])

    def test_run_that_read_a_skipped_doc_fails_naming_it(self):
        result = grade(['context-packs/gen/core/git-and-prs.md'], skips='git-and-prs.md')

        self.assertFalse(result['pass'])
        self.assertIn("shouldn't have read: git-and-prs.md", result['reason'])

    def test_run_expecting_no_docs_fails_on_reading_one(self):
        result = grade(['context-packs/project/releasing.md'])

        self.assertFalse(result['pass'])
        self.assertIn("shouldn't have read: context-packs/project/releasing.md", result['reason'])

    def test_run_expecting_no_docs_passes_on_reading_files_outside_context_packs(self):
        result = grade(['README.md', 'src/dates.ts'])

        self.assertTrue(result['pass'], result['reason'])

    def test_docs_names_another_folder_of_docs(self):
        result = grade(['agent-config/packs/core/testing.md', 'context-packs/core/pack.md'], docs='packs/core/')

        self.assertFalse(result['pass'])
        self.assertIn("shouldn't have read: packs/core/testing.md", result['reason'])
        self.assertNotIn('context-packs/core/pack.md', result['reason'])

    def test_reason_lists_every_doc_the_run_read(self):
        result = grade(['context-packs/gen/core/testing.md', 'src/dates.ts', 'context-packs/gen/core/writing-for-humans.md'],
                       reads='testing.md')

        self.assertTrue(result['pass'], result['reason'])
        self.assertIn('read: context-packs/gen/core/testing.md, context-packs/gen/core/writing-for-humans.md',
                      result['reason'])


if __name__ == '__main__':
    unittest.main()
