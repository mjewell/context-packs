from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('npm'), 'the npm package runs under node')
class NpmBinTests(unittest.TestCase):
    """The npm package's bin, which npx runs, runs the CLI that packing the package compiled."""

    @classmethod
    def setUpClass(cls):
        temp = tempfile.TemporaryDirectory(prefix='context-packs-package-')
        cls.addClassCleanup(temp.cleanup)
        folder = Path(temp.name)
        subprocess.run(['npm', 'pack', '--silent', '--pack-destination', str(folder)], cwd=ROOT, check=True,
                       capture_output=True)
        [tarball] = folder.glob('*.tgz')
        with tarfile.open(tarball) as archive:
            archive.extractall(folder)
        cls.bin = folder / 'package' / 'bin' / 'context-packs.js'

    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='context-packs-test-')
        self.addCleanup(temp.cleanup)
        self.repo = Path(temp.name)
        (self.repo / '.git').mkdir()

    def test_bin_runs_the_cli_in_the_current_folder(self):
        result = subprocess.run(['node', str(self.bin)], cwd=self.repo, text=True, capture_output=True, timeout=30)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.repo / 'AGENTS.md').read_text().startswith('<!-- context-packs:start -->\n'))

    def test_bin_passes_the_clis_failure_through(self):
        result = subprocess.run(['node', str(self.bin), 'remove', 'acme'], cwd=self.repo,
                                text=True, capture_output=True, timeout=30)

        self.assertEqual(result.returncode, 1)
        self.assertIn('context-packs: ', result.stderr)
        self.assertIn('acme', result.stderr)
