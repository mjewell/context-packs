from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / 'bin' / 'context-packs.js'


@unittest.skipUnless(shutil.which('node'), 'the npm package runs under node')
class NpmBinTests(unittest.TestCase):
    """The npm package's bin, which npx runs, hands its arguments to the Python CLI."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='context-packs-test-')
        self.addCleanup(temp.cleanup)
        self.repo = Path(temp.name)
        (self.repo / '.git').mkdir()

    def test_bin_runs_the_cli_in_the_current_folder(self):
        result = subprocess.run(['node', str(BIN)], cwd=self.repo, text=True, capture_output=True, timeout=30)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.repo / 'AGENTS.md').read_text().startswith('<!-- context-packs:start -->\n'))

    def test_bin_passes_the_clis_failure_through(self):
        result = subprocess.run(['node', str(BIN), 'remove', 'acme'], cwd=self.repo,
                                text=True, capture_output=True, timeout=30)

        self.assertEqual(result.returncode, 1)
        self.assertIn('context-packs: ', result.stderr)
        self.assertIn('acme', result.stderr)
