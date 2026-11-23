import json
from pathlib import Path
import re
import shlex
import subprocess
import sys

from review_wizard_case import REVIEW, StartedCase, WizardCase, deviation


class BriefTests(WizardCase):
    """brief gives one finder its prompt: the skill's prompt for its kind of finder, with the commands that read its
    docs and the change, and where its answer goes."""

    def setUp(self):
        super().setUp()
        self.init()

    def brief(self, finder):
        run = self.wizard('--run', self.run_dir, 'brief', finder)
        self.assertEqual(run.returncode, 0, run.stderr)
        return run.stdout

    def test_names_each_of_a_units_docs_with_the_command_that_reads_it(self):
        brief = self.brief('1')

        self.assertTrue(brief.startswith("You're checking one unit of a pack review."), brief[:80])
        self.assertIn(f'- `docs/testing.md`: run `{self.command("doc", "1", "1")}`\n'
                      f'- `docs/git.md`: run `{self.command("doc", "1", "2")}`\n', brief)
        self.assertNotIn('prose.md', brief)
        self.assertIn('Read each doc only through its command, so the review knows it was read.', brief)
        self.assertIn(f'`{self.command("files")}`', brief)
        self.assertIn(f'`{self.command("diff", "<path>")}`', brief)
        self.assertIn('Run each command exactly as it is printed here, one per Bash call, with no variables, `cd` or '
                      '`&&` around it.', brief)
        self.assertIn('Read the code at the head in the current folder.', brief)
        self.assertNotIn('Grep', brief)
        self.assertIn(f"Write your answer as JSON to `{self.answer_path('unit-1.json')}`, with your tool for writing "
                      'files, not the shell. Then run exactly this command, and do what it prints:\n\n'
                      f"{self.command('submit', '1')}\n\n"
                      'Your answer must fit this JSON Schema:\n\n{\n "type": "object",', brief)
        self.assertIn('"take"', brief)
        for placeholder in ('{diff}', '{log}', '{docs}'):
            self.assertNotIn(placeholder, brief)

    def test_gives_the_uncovered_finder_every_units_docs_to_search(self):
        brief = self.brief('3')

        self.assertTrue(brief.startswith("You're looking for the choices a change makes that no rule covers"),
                        brief[:80])
        self.assertIn('- `AGENTS.md`\n- `docs/testing.md`\n- `docs/git.md`\n- `docs/prose.md`\n', brief)
        self.assertNotIn(self.command('doc'), brief)
        self.assertIn('Each choice is one finding of kind `uncovered choice`', brief)
        self.assertIn(f"`{self.answer_path('unit-3.json')}`", brief)
        self.assertIn(f"\n\n{self.command('submit', '3')}\n\n", brief)

    def test_refuses_a_finder_init_didnt_name(self):
        run = self.wizard('--run', self.run_dir, 'brief', '4')

        self.assertEqual(run.returncode, 1)
        self.assertIn('There is no finder 4: init named finders 0 to 3.', run.stderr)


class DocTests(StartedCase):
    """doc prints one of a unit's docs, as the file is at the head."""

    def test_prints_the_doc_a_units_brief_numbers(self):
        run = self.step('doc', '1', '2')

        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout, '# Git\n\nSmall commits.\n')

    def test_refuses_a_doc_the_unit_doesnt_have(self):
        run = self.step('doc', '1', '3')

        self.assertEqual(run.returncode, 1)
        self.assertIn('Unit 1 has 2 docs.', run.stderr)

    def test_refuses_the_uncovered_finder_which_reads_docs_with_its_own_tools(self):
        run = self.step('doc', '3', '1')

        self.assertEqual(run.returncode, 1)
        self.assertIn('The uncovered finder has no docs to read through doc: search them in the current folder.',
                      run.stderr)


class ShellTests(WizardCase):
    """The submit command a brief prints works as written, run through a shell, once the answer is where the brief
    says to write it."""

    def test_the_briefs_submit_command_takes_the_answer_the_brief_named_through_bash(self):
        launcher = f'{shlex.quote(sys.executable)} {shlex.quote(str(REVIEW / "wizard.py"))}'
        run = self.wizard('init', '--base', self.base, '--head', 'HEAD', '--command', launcher)
        self.assertEqual(run.returncode, 0, run.stderr)
        brief = re.search(r'Run `(.+ brief 3)`', run.stdout).group(1)
        text = subprocess.run(['bash', '-c', brief], cwd=self.repo, env=self.env, capture_output=True,
                              text=True).stdout
        command = re.search(r'\n\n(.+ submit 3)\n', text).group(1)
        answer = Path(re.search(r'Write your answer as JSON to `(.+?)`', text).group(1))
        answer.write_text(json.dumps({'findings': [{**deviation('Quote "{this}"'), 'kind': 'uncovered choice',
                                                     'rules': []}]}))

        submitted = subprocess.run(['bash', '-c', command], cwd=self.repo, env=self.env, stdin=subprocess.DEVNULL,
                                   capture_output=True, text=True)

        self.assertEqual(submitted.returncode, 0, submitted.stderr)
        self.assertIn("The uncovered finder's answer is in, with 1 finding.", submitted.stdout)
