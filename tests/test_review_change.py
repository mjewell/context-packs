import hashlib
import json
import os
import re
import subprocess
import tempfile

from git_case import GitCase
from scripts import command


# An instruction file with an empty context-packs block, as a sync writes it, so the wizard has its one unit.
AGENTS = ('<!-- context-packs:start -->\n'
          f'<!-- context-packs:end sha256:{hashlib.sha256(b"").hexdigest()[:12]} -->\n')
TWELVE = ''.join(f'l{n}\n' for n in range(1, 13))


def body(diff):
    """A diff from its first hunk on, without the header, whose index line holds hashes."""
    return diff[diff.index('@@'):]


class ChangeCase(GitCase):
    """A repo whose base has an instruction file, and the wizard reading the change from the base to the head, the way
    a finder reads it."""

    def setUp(self):
        super().setUp()
        self.base = self.commit('Add the instruction file', {'AGENTS.md': AGENTS})
        temp = tempfile.TemporaryDirectory(prefix='context-packs-runs-')
        self.addCleanup(temp.cleanup)
        self.env = {**{key: value for key, value in os.environ.items() if not key.startswith('GIT_')},
                    'TMPDIR': temp.name}
        self.run_dir = None

    def step(self, *args):
        """A wizard step for the change from the base to the head, starting the run on the first."""
        if self.run_dir is None:
            init = self.wizard('init', '--base', self.base, '--head', 'HEAD', '--command', 'review')
            self.assertEqual(init.returncode, 0, init.stderr)
            self.run_dir = re.search(r'review --run (\S+) ', init.stdout).group(1)
        return self.wizard('--run', self.run_dir, *args)

    def wizard(self, *args):
        return subprocess.run([*command('review/wizard'), *args], cwd=self.repo, env=self.env,
                              input='', capture_output=True, text=True)

    def text(self, *args):
        run = self.step(*args)
        self.assertEqual(run.returncode, 0, run.stderr)
        return run.stdout


class FilesTests(ChangeCase):
    """files lists what the change touches, so a finder can pick what to read and how many pages each takes."""

    def test_lists_each_changed_path_with_the_lines_in_its_diff(self):
        self.commit('Add two files', {'a.txt': 'one\ntwo\nthree\n', 'docs/b.md': 'b\n'})
        self.commit('Change one', {'a.txt': 'one\n2\nthree\n'})

        # A new file's diff is six lines of header and a line for each line it holds.
        self.assertEqual(self.text('files'), '9\ta.txt\n7\tdocs/b.md\n')

    def test_lists_a_rename_as_a_deleted_path_and_an_added_one(self):
        self.commit('Add', {'old.txt': 'x\n'})
        self.base = self.git('rev-parse', 'HEAD')
        self.git('mv', 'old.txt', 'new.txt')
        self.commit('Rename')

        self.assertEqual(self.text('files'), '7\tnew.txt\n7\told.txt\n')


class ShownTests(ChangeCase):
    """The report reads the head lines each diff shows, since a review comment can be left only on one of them."""

    def test_prints_the_head_lines_each_diff_shows(self):
        self.commit('Add', {'a.txt': TWELVE, 'gone.txt': 'x\n'})
        self.base = self.git('rev-parse', 'HEAD')
        self.commit('Change line 10 and delete a file', {'a.txt': TWELVE.replace('l10\n', 'ten\n')},
                    removed=['gone.txt'])

        run = subprocess.run([*command('review/change'), '--base', self.base, '--head', 'HEAD',
                              'shown'], cwd=self.repo, capture_output=True, text=True, check=True)

        self.assertEqual(json.loads(run.stdout), {'a.txt': [7, 8, 9, 10, 11, 12], 'gone.txt': []})


class DiffTests(ChangeCase):
    """diff shows one path's change, with each line the head has numbered as it is there, so a finding can name a
    line without counting."""

    def test_numbers_each_line_the_head_has_and_leaves_removed_lines_blank(self):
        self.commit('Add', {'a.txt': TWELVE})
        self.base = self.git('rev-parse', 'HEAD')
        self.commit('Change line 10', {'a.txt': TWELVE.replace('l10\n', 'ten\n')})

        diff = self.text('diff', 'a.txt')

        self.assertTrue(diff.startswith('diff --git a/a.txt b/a.txt\n'), diff)
        self.assertEqual(body(diff), '@@ -7,6 +7,6 @@ l6\n'
                                     ' 7  l7\n'
                                     ' 8  l8\n'
                                     ' 9  l9\n'
                                     '   -l10\n'
                                     '10 +ten\n'
                                     '11  l11\n'
                                     '12  l12\n')

    def test_numbers_each_hunk_from_its_own_start(self):
        self.commit('Add', {'a.txt': TWELVE})
        self.base = self.git('rev-parse', 'HEAD')
        self.commit('Change both ends', {'a.txt': 'one\n' + TWELVE[3:-4] + 'twelve\n'})

        self.assertEqual(body(self.text('diff', 'a.txt')), '@@ -1,4 +1,4 @@\n'
                                                           '   -l1\n'
                                                           ' 1 +one\n'
                                                           ' 2  l2\n'
                                                           ' 3  l3\n'
                                                           ' 4  l4\n'
                                                           '@@ -9,4 +9,4 @@ l8\n'
                                                           ' 9  l9\n'
                                                           '10  l10\n'
                                                           '11  l11\n'
                                                           '   -l12\n'
                                                           '12 +twelve\n')

    def test_leaves_the_no_newline_marker_unnumbered(self):
        self.commit('Add', {'a.txt': 'one\n'})
        self.base = self.git('rev-parse', 'HEAD')
        self.commit('Drop the newline', {'a.txt': 'one\ntwo'})

        self.assertEqual(body(self.text('diff', 'a.txt')), '@@ -1 +1,2 @@\n'
                                                           '1  one\n'
                                                           '2 +two\n'
                                                           '  \\ No newline at end of file\n')

    def test_shows_only_the_change_since_the_merge_base(self):
        self.commit('Add', {'a.txt': 'a\n', 'b.txt': 'b\n'})
        fork = self.git('rev-parse', 'HEAD')
        self.git('checkout', '-q', '-b', 'base')
        self.base = self.commit('Change b on the base branch', {'b.txt': 'base\n'})
        self.git('checkout', '-q', fork)
        self.commit('Change a on the PR', {'a.txt': 'pr\n'})

        self.assertEqual(self.text('files'), '7\ta.txt\n')
        self.assertIn("b.txt isn't one of the paths", self.step('diff', 'b.txt').stderr)

    def test_refuses_a_path_outside_the_change_however_it_is_written(self):
        self.commit('Add', {'a.txt': 'a\n'})

        for path in ('/etc/passwd', '../a.txt', 'docs/../a.txt', '..', '', '-p', '--output=x'):
            with self.subTest(path=path):
                run = self.step('diff', '--', path) if path.startswith('-') else self.step('diff', path)

                self.assertEqual(run.returncode, 1, run.stdout)
                self.assertIn(f"{path} isn't one of the paths", run.stderr)

    def test_reads_a_path_literally_not_as_a_pattern(self):
        self.commit('Add a file named like a pattern', {'*.txt': 'star\n', 'b.txt': 'b\n'})

        diff = self.text('diff', '*.txt')

        self.assertIn('+star', diff)
        self.assertNotIn('b.txt', diff)

    def test_runs_no_external_diff_or_textconv(self):
        script = self.repo.parent / f'{self.repo.name}-driver.sh'
        ran = self.repo.parent / f'{self.repo.name}-ran'
        script.write_text(f'#!/bin/sh\ntouch {ran}\necho converted\n')
        script.chmod(0o755)
        self.addCleanup(script.unlink)
        self.git('config', 'diff.external', str(script))
        self.git('config', 'diff.conv.textconv', str(script))
        self.commit('Add', {'.gitattributes': '*.txt diff=conv\n', 'a.txt': 'a\n'})
        self.commit('Change', {'a.txt': 'b\n'})

        self.text('diff', 'a.txt')

        self.assertFalse(ran.exists())


class PagingTests(ChangeCase):
    """Long output comes in pages of 1000 lines, so one step can't fill a finder's context."""

    def setUp(self):
        super().setUp()
        self.commit('Add a long file', {'long.txt': ''.join(f'{n}\n' for n in range(1, 2501))})

    def test_gives_the_first_page_and_says_how_to_get_the_next(self):
        lines = self.text('diff', 'long.txt').splitlines()

        self.assertEqual(len(lines), 1001)
        self.assertEqual(lines[999], ' 994 +994')
        self.assertEqual(lines[1000], '(page 1 of 3: run it again with page 2 for more)')

    def test_gives_a_later_page(self):
        lines = self.text('diff', 'long.txt', '3').splitlines()

        # The diff has 2506 lines: six of header, then one per line of the file.
        self.assertEqual(lines[0], '1995 +1995')
        self.assertEqual(lines[-2:], ['2500 +2500', '(page 3 of 3)'])

    def test_refuses_a_page_past_the_last_and_one_that_isnt_a_page(self):
        self.assertIn('long.txt has 3 pages.', self.step('diff', 'long.txt', '4').stderr)
        for page in ('0', 'two', '-1'):
            with self.subTest(page=page):
                run = self.step('diff', 'long.txt', page)

                self.assertEqual(run.returncode, 1)
                self.assertIn(f"{page!r} isn't a page: pages count from 1.", run.stderr)


class LogTests(ChangeCase):
    """log lists the change's commits with their messages, since a message can say a choice was deliberate."""

    def test_lists_the_changes_commits_newest_first_and_none_from_the_base_branch(self):
        self.commit('Add', {'a.txt': 'a\n'})
        fork = self.git('rev-parse', 'HEAD')
        self.git('checkout', '-q', '-b', 'base')
        self.base = self.commit('On the base branch', {'b.txt': 'b\n'})
        self.git('checkout', '-q', fork)
        first = self.commit('Change a\n\nThe reason.', {'a.txt': 'x\n'})
        second = self.commit('Add c', {'c.txt': 'c\n'})

        text = self.text('log')

        self.assertEqual(re.findall(r'^commit (\w+)$', text, re.M), [second, first])
        self.assertIn('    Change a\n    \n    The reason.\n', text)
        self.assertNotIn('On the base branch', text)
