import unittest

from test_cli import SyncCase, doc


class CheckTests(SyncCase):
    """check, which exits 1 when a sync would change anything, and writes nothing."""

    def test_synced_repo_passes_silently(self):
        self.share('Prefer small PRs.\n')
        self.add()
        before = self.agents_md.read_text()

        result = self.sync('check')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, '')
        self.assertEqual(self.agents_md.read_text(), before)

    def test_when_changed_without_a_resync_fails_naming_the_block(self):
        self.write('context-packs/testing.md', doc('Writing tests'))
        self.sync()
        before = self.agents_md.read_text()
        self.write('context-packs/testing.md', doc('Writing or changing tests'))

        result = self.sync('check')

        self.assertEqual(result.returncode, 1)
        self.assertIn(f'{self.agents_md}: the context-packs block is stale', result.stderr)
        self.assertIn('npx context-packs', result.stderr)
        self.assertEqual(self.agents_md.read_text(), before)

    def test_ref_edited_without_a_resync_fails_naming_the_stale_generated_file(self):
        old = self.publish({'pack.md': 'Prefer small PRs.\n', 'testing.md': doc('Writing tests', 'Use factories.\n')})
        self.add()
        new = self.publish({'testing.md': doc('Writing tests', 'Use fixtures.\n')})
        self.import_md().write_text(self.import_md().read_text().replace(old, new))
        synced = self.gen / 'house-rules' / 'testing.md'

        result = self.sync('check')

        self.assertEqual(result.returncode, 1)
        self.assertIn('context-packs/gen/house-rules/testing.md', result.stderr)
        self.assertEqual(synced.read_text(), doc('Writing tests', 'Use factories.\n'))

    def test_repo_never_synced_fails_creating_nothing(self):
        result = self.sync('check')

        self.assertEqual(result.returncode, 1)
        self.assertIn(f"context-packs: {self.agents_md} doesn't exist", result.stderr)
        self.assertEqual(sorted(p.name for p in self.repo.iterdir()), ['.git'])

    def test_block_edited_in_the_repo_fails_untouched(self):
        self.share('Prefer small PRs.\n')
        self.add()
        edited = self.agents_md.read_text().replace('small PRs', 'tiny PRs')
        self.agents_md.write_text(edited)

        result = self.sync('check')

        self.assertEqual(result.returncode, 1)
        self.assertIn('was edited', result.stderr)
        self.assertEqual(self.agents_md.read_text(), edited)


if __name__ == '__main__':
    unittest.main()
