import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest

from git_case import REVIEW, GitCase

ROOT = REVIEW.parent

# The block as a sync writes it, so the CLI's check that it wasn't edited passes.
BODY = '''## Context

| When | Read |
|---|---|
| Writing tests | `docs/testing.md` |
| Committing | `docs/git.md` |

## style context

| When | Read |
|---|---|
| Writing prose | `docs/prose.md` |
'''
AGENTS = ('# Repo\n\n<!-- context-packs:start -->\n' + BODY
          + f'<!-- context-packs:end sha256:{hashlib.sha256(BODY.encode()).hexdigest()[:12]} -->\n')
DOCS = {'docs/testing.md': '# Testing\n\nTest behavior.\n', 'docs/git.md': '# Git\n\nSmall commits.\n',
        'docs/prose.md': '# Prose\n\nShort sentences.\n'}


class WizardCase(GitCase):
    """A repo whose instruction file has two packs' tables, so the review has two pack units after the instruction
    file's, and a change on top of its base that edits one file and adds another. The wizard runs in it the way an
    agent runs it, as a command."""

    def setUp(self):
        super().setUp()
        self.commit('Add the packs and the app', {'AGENTS.md': AGENTS, **DOCS, 'src/app.py': 'x = 1\n'})
        self.base = self.git('rev-parse', 'HEAD')
        self.head = self.commit('Change the app', {'src/app.py': 'x = 2\n', 'tests/test_app.py': 'assert True\n'})
        temp = tempfile.TemporaryDirectory(prefix='context-packs-runs-')
        self.addCleanup(temp.cleanup)
        self.env = {**{key: value for key, value in os.environ.items() if not key.startswith('GIT_')},
                    'TMPDIR': temp.name}
        self.run_dir = None

    def wizard(self, *args):
        return subprocess.run([sys.executable, str(REVIEW / 'wizard.py'), *args], cwd=self.repo, env=self.env,
                              capture_output=True, text=True)

    def init(self):
        """What init printed, once it succeeded. The run folder it made is in every command it prints."""
        run = self.wizard('init', '--base', self.base, '--head', 'HEAD', '--command', 'review')
        self.assertEqual(run.returncode, 0, run.stderr)
        self.run_dir = re.search(r'review --run (\S+) ', run.stdout).group(1)
        return run.stdout

    def command(self, *args):
        """A command as the wizard prints it for this run."""
        return ' '.join(['review', '--run', self.run_dir, *args])


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

    def test_refuses_a_checkout_that_isnt_the_head(self):
        self.git('checkout', '-q', self.base)

        run = self.wizard('init', '--base', self.base, '--head', self.head, '--command', 'review')

        self.assertEqual(run.returncode, 1)
        self.assertIn(f"The checkout isn't the head, {self.head}.", run.stderr)
        self.assertEqual(run.stdout, '')


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
        self.assertIn(f'Write your answer to `{self.run_dir}/answers/unit-1.json`, in the shape '
                      f'`{self.run_dir}/findings.schema.json` sets. Then run `{self.command("submit", "1")}`', brief)
        self.assertNotIn('{', brief)

    def test_gives_the_uncovered_finder_every_units_docs_to_search(self):
        brief = self.brief('3')

        self.assertTrue(brief.startswith("You're looking for the choices a change makes that no rule covers"),
                        brief[:80])
        self.assertIn('- `AGENTS.md`\n- `docs/testing.md`\n- `docs/git.md`\n- `docs/prose.md`\n', brief)
        self.assertNotIn(' doc ', brief)
        self.assertIn('Each choice is one finding of kind `uncovered choice`', brief)
        self.assertIn(f'Then run `{self.command("submit", "3")}`', brief)

    def test_refuses_a_finder_init_didnt_name(self):
        run = self.wizard('--run', self.run_dir, 'brief', '4')

        self.assertEqual(run.returncode, 1)
        self.assertIn('There is no finder 4: init named finders 0 to 3.', run.stderr)


class StartedCase(WizardCase):
    """A run init started."""

    def setUp(self):
        super().setUp()
        self.init()

    def step(self, *args):
        """A step of this run: what it printed, and what it printed as an error, with its exit code."""
        return self.wizard('--run', self.run_dir, *args)


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
        self.assertIn('The uncovered finder has no docs to read through doc: search them with Read, Glob and Grep.',
                      run.stderr)


class ChangeTests(StartedCase):
    """files, diff and log read the change from the merge base to the head, the way the git server does."""

    def test_files_lists_each_changed_path_with_the_lines_in_its_diff(self):
        run = self.step('files')

        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout, '7\tsrc/app.py\n7\ttests/test_app.py\n')

    def test_diff_numbers_each_line_the_head_has(self):
        run = self.step('diff', 'src/app.py')

        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertTrue(run.stdout.endswith('@@ -1 +1 @@\n  -x = 1\n1 +x = 2\n'), run.stdout)

    def test_diff_refuses_a_path_the_change_doesnt_touch(self):
        run = self.step('diff', 'docs/git.md')

        self.assertEqual(run.returncode, 1)
        self.assertIn(f"docs/git.md isn't one of the paths `{self.command('files')}` lists.", run.stderr)

    def test_log_lists_the_changes_commits_only(self):
        run = self.step('log')

        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn('Change the app', run.stdout)
        self.assertNotIn('Add the packs', run.stdout)


def deviation(headline='Tests reach into a private helper', path='tests/test_app.py', line=1):
    return {'kind': 'deviation', 'headline': headline,
            'rules': [{'file': 'docs/testing.md', 'quote': 'Test behavior.', 'routed': True}],
            'spots': [{'path': path, 'line': line, 'follows': False}], 'deliberate': [], 'exemplars': [],
            'take': 'Test through the public interface.'}


class SubmitCase(StartedCase):
    """A finder at the end of its brief: it read its docs and wrote its answer."""

    def answer(self, finder, findings):
        path = Path(self.run_dir) / 'answers' / f'unit-{finder}.json'
        path.write_text(findings if isinstance(findings, str) else json.dumps({'findings': findings}))

    def read_docs(self, unit, count):
        for n in range(1, count + 1):
            run = self.step('doc', str(unit), str(n))
            self.assertEqual(run.returncode, 0, run.stderr)

    def submit_unit(self, unit, docs, findings):
        self.read_docs(unit, docs)
        self.answer(unit, findings)
        run = self.step('submit', str(unit))
        self.assertEqual(run.returncode, 0, run.stderr)


class SubmitTests(SubmitCase):
    """submit takes a finder's answer only when it's whole: in the schema's shape, and after every doc of its unit was
    read through doc. A refusal says what to do, then to submit again."""

    def test_takes_an_answer_once_every_doc_was_read(self):
        self.read_docs(1, 2)
        self.answer(1, [deviation()])

        run = self.step('submit', '1')

        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout, 'Unit 1 is in, with 1 finding. Tell whoever started you that unit 1 is in, and '
                                     'stop.\n')

    def test_refuses_an_answer_before_every_doc_was_read_and_names_the_commands_left(self):
        self.read_docs(1, 1)
        self.answer(1, [deviation()])

        run = self.step('submit', '1')

        self.assertEqual(run.returncode, 1)
        self.assertEqual(run.stdout, '')
        self.assertIn(f"Not taken: you didn't read docs/git.md through `{self.command('doc', '1', '2')}`. Read it, "
                      f"check the diff against it, update your answer, then run `{self.command('submit', '1')}` again.",
                      run.stderr)
        self.assertFalse((Path(self.run_dir) / 'accepted' / 'unit-1.json').exists())

    def test_takes_the_uncovered_finders_answer_without_any_doc_read(self):
        self.answer(3, [])

        run = self.step('submit', '3')

        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout, "The uncovered finder's answer is in, with 0 findings. Tell whoever started you "
                                     "that the uncovered finder's answer is in, and stop.\n")

    def test_refuses_an_answer_that_breaks_the_schema_and_names_where(self):
        broken = deviation()
        broken['spots'][0]['line'] = '12'
        del broken['take']
        broken['kind'] = 'nit'
        self.read_docs(1, 2)
        self.answer(1, [broken])

        run = self.step('submit', '1')

        self.assertEqual(run.returncode, 1)
        self.assertIn(f'Not taken: your answer at {self.run_dir}/answers/unit-1.json breaks the schema:\n'
                      '  findings[0] needs take\n'
                      '  findings[0].kind must be one of "deviation", "conflict", "uncovered choice"\n'
                      '  findings[0].spots[0].line must be an integer\n'
                      f"Fix it, then run `{self.command('submit', '1')}` again.", run.stderr)

    def test_refuses_an_answer_with_a_key_the_schema_doesnt_have(self):
        extra = {**deviation(), 'severity': 'high'}
        self.read_docs(1, 2)
        self.answer(1, [extra])

        run = self.step('submit', '1')

        self.assertEqual(run.returncode, 1)
        self.assertIn('  findings[0] has severity, which the schema has no place for\n', run.stderr)

    def test_refuses_an_answer_that_isnt_json(self):
        self.read_docs(1, 2)
        self.answer(1, '{"findings": [')

        run = self.step('submit', '1')

        self.assertEqual(run.returncode, 1)
        self.assertIn(f"Not taken: your answer at {self.run_dir}/answers/unit-1.json isn't JSON", run.stderr)

    def test_refuses_when_there_is_no_answer_yet(self):
        self.read_docs(1, 2)

        run = self.step('submit', '1')

        self.assertEqual(run.returncode, 1)
        self.assertIn(f"Not taken: there's no answer at {self.run_dir}/answers/unit-1.json. Write it, then run "
                      f"`{self.command('submit', '1')}` again.", run.stderr)


class NextTests(SubmitCase):
    """next tells the orchestrator what to do now, from what the run folder holds, so it can also pick a run back up."""

    def test_names_each_finder_whose_answer_isnt_in_with_its_prompt(self):
        self.submit_unit(0, 1, [])
        self.submit_unit(2, 1, [])

        run = self.step('next')

        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout,
                         "Waiting on 2 finders, whose answers aren't in yet:\n"
                         f'  unit 1, 2 docs: Run `{self.command("brief", "1")}` and follow what it says.\n'
                         f'  the uncovered finder: Run `{self.command("brief", "3")}` and follow what it says.\n'
                         'If one of them stopped without its answer going in, start it again with the same prompt. '
                         f'When they have all answered, run `{self.command("next")}` again.\n')

    def test_starts_the_merge_once_every_finder_is_in_and_numbers_their_findings(self):
        self.submit_unit(0, 1, [deviation('A')])
        self.submit_unit(1, 2, [deviation('B'), deviation('C')])
        self.submit_unit(2, 1, [])
        self.answer(3, [{**deviation('D'), 'kind': 'uncovered choice', 'rules': []}])
        self.assertEqual(self.step('submit', '3').returncode, 0)

        run = self.step('next')

        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout, 'All 4 finders are in, with 4 findings.\n'
                                     'Start one subagent with exactly this prompt: Run '
                                     f'`{self.command("brief", "merge")}` and follow what it says.\n'
                                     f'When it has answered, run `{self.command("next")}`.\n')
        sources = json.loads((Path(self.run_dir) / 'sources.json').read_text())
        self.assertEqual([(source['id'], source['finding']['headline']) for source in sources],
                         [('0:0', 'A'), ('1:0', 'B'), ('1:1', 'C'), ('3:0', 'D')])

    def test_keeps_the_finders_answers_once_the_merge_has_started(self):
        for unit, docs in ((0, 1), (1, 2), (2, 1)):
            self.submit_unit(unit, docs, [])
        self.answer(3, [])
        self.step('submit', '3')
        self.step('next')

        run = self.step('submit', '1')

        self.assertEqual(run.returncode, 1)
        self.assertIn("Not taken: the merge has started, so the finders' answers can't change.", run.stderr)


class MergeTests(SubmitCase):
    """Once every finder is in, one subagent groups their findings, and the wizard builds the findings from its groups,
    as the merge job's script does."""

    def all_in(self):
        self.submit_unit(0, 1, [deviation('A')])
        self.submit_unit(1, 2, [deviation('B')])
        self.submit_unit(2, 1, [])
        self.answer(3, [{**deviation('D'), 'kind': 'uncovered choice', 'rules': []}])
        self.assertEqual(self.step('submit', '3').returncode, 0)
        self.assertEqual(self.step('next').returncode, 0)

    def groups(self, groups):
        (Path(self.run_dir) / 'answers' / 'groups.json').write_text(json.dumps({'groups': groups}))

    def test_brief_gives_the_merging_agent_the_numbered_findings_and_where_its_groups_go(self):
        self.all_in()

        run = self.step('brief', 'merge')

        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertTrue(run.stdout.startswith("You're merging the finders' answers in a pack review"), run.stdout[:80])
        self.assertIn(f"Every finder's findings are in `{self.run_dir}/sources.json`, each with an id.", run.stdout)
        self.assertIn(f'Write your groups to `{self.run_dir}/answers/groups.json`, in the shape '
                      f'`{self.run_dir}/groups.schema.json` sets. Then run `{self.command("submit-groups")}`',
                      run.stdout)

    def test_brief_refuses_the_merge_before_every_finder_is_in(self):
        run = self.step('brief', 'merge')

        self.assertEqual(run.returncode, 1)
        self.assertIn(f"The merge can't start yet: run `{self.command('next')}` to see whose answers aren't in.",
                      run.stderr)

    def test_next_waits_on_the_merge_until_its_groups_are_in(self):
        self.all_in()

        run = self.step('next')

        self.assertEqual(run.stdout, "Waiting on the merge, whose groups aren't in yet. If it stopped without its "
                                     'groups going in, start it again with the same prompt: Run '
                                     f'`{self.command("brief", "merge")}` and follow what it says. When it has '
                                     f'answered, run `{self.command("next")}` again.\n')

    def test_refuses_groups_that_leave_out_a_finders_finding(self):
        self.all_in()
        self.groups([{'ids': ['0:0', '1:0'], 'kind': 'deviation', 'headline': 'H', 'take': 'T'}])

        run = self.step('submit-groups')

        self.assertEqual(run.returncode, 1)
        self.assertIn("Not taken: the merge's groups leave out 3:0. Fix your groups, then run "
                      f"`{self.command('submit-groups')}` again.", run.stderr)

    def test_builds_the_findings_from_the_groups_and_next_says_its_done(self):
        self.all_in()
        self.groups([{'ids': ['0:0', '1:0'], 'kind': 'deviation', 'headline': 'One import, two rules', 'take': 'T'},
                     {'ids': ['3:0'], 'kind': 'uncovered choice', 'headline': 'Where config lives', 'take': 'U'}])

        run = self.step('submit-groups')

        self.assertEqual(run.returncode, 0, run.stderr)
        path = f'{self.run_dir}/findings.json'
        self.assertEqual(run.stdout, f'2 findings are in {path}. Tell whoever started you, and stop.\n')
        report = json.loads(Path(path).read_text())
        self.assertEqual((report['base'], report['head']), (self.base, self.head))
        self.assertEqual([(found['headline'], len(found['rules']), found['take']) for found in report['findings']],
                         [('One import, two rules', 1, 'T'), ('Where config lives', 0, 'U')])
        self.assertEqual(self.step('next').stdout,
                         f'Done: 2 findings, 1 deviation and 1 uncovered choice, in {path}.\n')


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
