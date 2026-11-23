from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile
import unittest

from review_wizard_case import ROOT, WizardCase


class InitTests(WizardCase):
    """init sets up a run and tells the orchestrator which finders to start, one per unit and the uncovered finder,
    each with the one-line prompt it gives that finder."""

    def test_names_a_finder_for_each_unit_and_the_uncovered_finder(self):
        out = self.init()

        self.assertIn(f'unit 0, AGENTS.md: Run `{self.command("brief", "0")}` and follow what it says.', out)
        self.assertIn(f'unit 1, 2 docs: Run `{self.command("brief", "1")}` and follow what it says.', out)
        self.assertIn(f'unit 2, 1 doc: Run `{self.command("brief", "2")}` and follow what it says.', out)
        self.assertIn(f'the uncovered finder: Run `{self.command("brief", "3")}` and follow what it says.', out)
        self.assertIn(f'When all of them have answered, run `{self.command("next")}`.', out)
        self.assertTrue(Path(self.run_dir).is_dir())

    def test_refuses_a_change_that_touches_no_files(self):
        run = self.wizard('init', '--base', 'HEAD', '--head', 'HEAD', '--command', 'review')

        self.assertEqual(run.returncode, 1)
        self.assertIn('The change from', run.stderr)
        self.assertIn('touches no files, so there is nothing to review.', run.stderr)

    def test_refuses_a_checkout_that_isnt_the_head(self):
        self.git('checkout', '-q', self.base)

        run = self.wizard('init', '--base', self.base, '--head', self.head, '--command', 'review')

        self.assertEqual(run.returncode, 1)
        self.assertIn(f"The checkout isn't the head, {self.head}.", run.stderr)
        self.assertEqual(run.stdout, '')


class ArgumentTests(WizardCase):
    """Claude Code's allow rule passes any arguments after the wizard's command, so the wizard takes only the ones it
    names, spelled out."""

    def test_refuses_an_option_cut_short(self):
        run = self.wizard('init', '--base', self.base, '--head', 'HEAD', '--comm', 'review')

        self.assertEqual(run.returncode, 2)
        self.assertIn('the following arguments are required: --command', run.stderr)

    def test_refuses_an_argument_a_step_doesnt_take(self):
        self.init()

        run = self.wizard('--run', self.run_dir, 'files', '--output=x')

        self.assertEqual(run.returncode, 2)
        self.assertIn('unrecognized arguments: --output=x', run.stderr)


@unittest.skipUnless(shutil.which('npm') and shutil.which('node'), 'the npm package runs under node')


class PackageTests(WizardCase):
    """A local review runs the wizard as `npx context-packs@<version> review`, from the npm package alone."""

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

    def packaged(self, *args):
        return subprocess.run(['node', str(self.bin), 'review', *args], cwd=self.repo, env=self.env,
                              capture_output=True, text=True)

    def test_runs_the_wizards_steps_from_the_package(self):
        run = self.packaged('init', '--base', self.base, '--head', 'HEAD', '--command', 'review')
        self.assertEqual(run.returncode, 0, run.stderr)
        self.run_dir = re.search(r'review --run (\S+) ', run.stdout).group(1)

        brief = self.packaged('--run', self.run_dir, 'brief', '1')

        self.assertEqual(brief.returncode, 0, brief.stderr)
        self.assertTrue(brief.stdout.startswith("You're checking one unit of a pack review."), brief.stdout[:80])

    def test_passes_a_refusal_through(self):
        run = self.packaged('init', '--base', self.base, '--head', self.base, '--command', 'review')

        self.assertEqual(run.returncode, 1)
        self.assertIn("The checkout isn't the head", run.stderr)
