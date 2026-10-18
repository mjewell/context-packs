import unittest

from test_cli import EMPTY, SyncCase, doc


class ReportTests(SyncCase):
    """What a sync prints about the changes it made."""

    def setUp(self):
        super().setUp()
        self.first = self.share('Prefer small PRs.\n')
        self.sync()

    def test_add_names_the_pack_and_its_ref(self):
        result = self.add()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, f'house-rules: added @ {self.first[:7]}\n')

    def test_remove_names_the_pack(self):
        self.add()

        result = self.sync('remove', 'house-rules')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'house-rules: removed\n')

    def test_update_shows_where_the_pack_moved(self):
        self.add()
        latest = self.share('Prefer small PRs.\nWrite tests first.\n')

        result = self.sync('update')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, f'house-rules: {self.first[:7]} → {latest[:7]}\n')

    def test_update_lists_every_pack_it_covers(self):
        self.add()
        steady_origin, steady = self.remote('steady')
        steady_ref = self.publish({'pack.md': 'Use steady.\n'}, checkout=steady)
        self.sync('add', 'steady', str(steady_origin), '--path', 'context')
        tagged_origin, tagged = self.remote('tagged')
        self.publish({'pack.md': 'Use tagged.\n'}, checkout=tagged)
        self.tag('v1.0.0', checkout=tagged)
        self.sync('add', 'tagged', str(tagged_origin), '--path', 'context', '--ref', 'v1.0.0')
        latest = self.share('Prefer small PRs.\nWrite tests first.\n')

        result = self.sync('update')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, f'house-rules: {self.first[:7]} → {latest[:7]}\n'
                                        f'steady: {steady_ref[:7]} (up to date)\n'
                                        'tagged: v1.0.0 (tag)\n')

    def test_update_to_another_tag_shows_the_tags_in_full(self):
        self.tag('v1.0.0')
        self.add('--ref', 'v1.0.0')
        self.share('Prefer small PRs.\nWrite tests first.\n')
        self.tag('v1.1.0')

        result = self.sync('update', 'house-rules', '--ref', 'v1.1.0')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'house-rules: v1.0.0 → v1.1.0\n')

    def test_update_lists_no_folder_on_disk(self):
        self.sync('add', 'house-rules', '../house-rules', '--path', 'context')

        result = self.sync('update')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'Nothing changed: house-rules\n')

    def test_resync_with_nothing_to_change_says_so_and_names_the_pins(self):
        self.add()
        self.share('Prefer small PRs.\nWrite tests first.\n')

        result = self.sync()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, f'Nothing changed: house-rules @ {self.first[:7]}\n')

    def test_resync_without_import_packs_says_nothing_changed(self):
        result = self.sync()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'Nothing changed\n')

    def test_add_of_a_folder_on_disk_names_no_ref(self):
        self.write('team-rules/pack.md', 'Use pnpm.\n')

        result = self.sync('add', 'team', 'team-rules')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'team: added\n')

    def test_resync_after_the_repos_own_docs_change_says_the_block_changed(self):
        self.write('context-packs/design.md', doc('Changing the design'))

        result = self.sync()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'Updated the context-packs block\n')

    def test_filling_a_pasted_block_says_so(self):
        self.agents_md.write_text('# Repo\n\n' + EMPTY)

        result = self.sync()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'Updated the context-packs block\n')

    def test_first_sync_says_it_created_agents_md_and_linked_claude_md(self):
        self.agents_md.unlink()
        (self.repo / 'CLAUDE.md').unlink()

        result = self.sync()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'Created AGENTS.md\nLinked CLAUDE.md to AGENTS.md\n')

    def test_resync_after_claude_md_is_deleted_leaves_it_deleted(self):
        (self.repo / 'CLAUDE.md').unlink()

        result = self.sync()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'Nothing changed\n')
        self.assertFalse((self.repo / 'CLAUDE.md').is_symlink())


if __name__ == '__main__':
    unittest.main()
