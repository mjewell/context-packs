import unittest

from test_cli import CLAUSE, SyncCase, doc


def rows(*pairs):
    return '## Context\n\n| When | Read |\n|---|---|\n' + ''.join(f'| {when} | `{path}` |\n' for when, path in pairs)


class OutsideRepoTests(SyncCase):
    """A folder in no git repo, such as the one above the repos: sessions start anywhere, so rows are absolute."""

    def setUp(self):
        super().setUp()
        (self.repo / '.git').rmdir()

    def test_rows_are_absolute(self):
        self.write('context-packs/testing.md', doc('Writing tests'))

        result = self.sync()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(rows(('Writing tests', f'{self.repo}/context-packs/testing.md')), self.agents())

    def test_header_doesnt_say_where_paths_start(self):
        result = self.sync()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(CLAUSE, self.agents())

    def test_a_nested_packs_index_has_absolute_rows(self):
        self.write('context-packs/web/pack.md', doc('Editing `web/**`'))
        self.write('context-packs/web/forms.md', doc('Building a form'))

        result = self.sync()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(rows(('Editing `web/**`', f'{self.repo}/context-packs/gen/web.md')), self.agents())
        self.assertIn(f'| Building a form | `{self.repo}/context-packs/web/forms.md` |',
                      (self.gen / 'web.md').read_text())


class SubfolderTests(SyncCase):
    """A folder inside a repo, such as a package with its own AGENTS.md: sessions start at the repo root, so rows start
    there too."""

    def test_rows_start_from_the_repo_root(self):
        self.write('packages/web/context-packs/testing.md', doc('Writing tests'))

        result = self.sync('--dir', str(self.repo / 'packages' / 'web'))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(rows(('Writing tests', 'packages/web/context-packs/testing.md')),
                      (self.repo / 'packages' / 'web' / 'AGENTS.md').read_text())

    def test_header_says_paths_start_from_the_repo_root(self):
        self.write('packages/web/context-packs/testing.md', doc('Writing tests'))

        result = self.sync('--dir', str(self.repo / 'packages' / 'web'))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f'read its doc. {CLAUSE}The packs here',
                      (self.repo / 'packages' / 'web' / 'AGENTS.md').read_text())

    def test_a_worktrees_git_file_marks_the_repo_root(self):
        (self.repo / '.git').rmdir()
        self.write('.git', 'gitdir: /elsewhere/.git/worktrees/repo\n')
        self.write('packages/web/context-packs/testing.md', doc('Writing tests'))

        result = self.sync('--dir', str(self.repo / 'packages' / 'web'))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(rows(('Writing tests', 'packages/web/context-packs/testing.md')),
                      (self.repo / 'packages' / 'web' / 'AGENTS.md').read_text())


if __name__ == '__main__':
    unittest.main()
