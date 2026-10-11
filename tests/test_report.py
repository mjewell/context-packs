import unittest

from test_cli import EMPTY_HEADER, SyncCase


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

    def test_add_names_the_nested_packs_it_picked(self):
        self.doc_set('typescript', {'pack.md': '---\nwhen: Editing `**/*.ts`\n---\nType it.\n'})
        latest = self.doc_set('skills', {'pack.md': '---\nwhen: Editing skills\n---\nKeep skills short.\n'})

        result = self.add('--docs', 'typescript,skills')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, f'house-rules: added @ {latest[:7]} (docs: skills, typescript)\n')

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

    def test_update_to_a_release_tag_shows_the_tags_in_full(self):
        self.tag('v1.0.0')
        self.add('--ref', 'v1.0.0')
        self.share('Prefer small PRs.\nWrite tests first.\n')
        self.tag('v1.1.0')

        result = self.sync('update')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'house-rules: v1.0.0 → v1.1.0\n')

    def test_resync_with_nothing_to_change_says_so_and_names_the_pins(self):
        self.add()
        self.share('Prefer small PRs.\nWrite tests first.\n')

        result = self.sync()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, f'Nothing changed: house-rules @ {self.first[:7]}\n')

    def test_resync_without_packs_says_nothing_changed(self):
        result = self.sync()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'Nothing changed: no packs installed\n')

    def test_docs_shows_the_picks_before_and_after(self):
        self.doc_set('typescript', {'pack.md': '---\nwhen: Editing `**/*.ts`\n---\nType it.\n'})
        self.doc_set('skills', {'pack.md': '---\nwhen: Editing skills\n---\nKeep skills short.\n'})
        self.add('--docs', 'skills')

        widened = self.sync('docs', 'house-rules', 'skills,typescript')
        emptied = self.sync('docs', 'house-rules', '')

        self.assertEqual(widened.stdout, 'house-rules: nested packs skills → skills, typescript\n')
        self.assertEqual(emptied.stdout, 'house-rules: nested packs skills, typescript → none\n')

    def project_doc(self, name, when):
        docs = self.repo / 'docs' / 'agents' / 'project'
        docs.mkdir(parents=True, exist_ok=True)
        (docs / f'{name}.md').write_text(f'---\nwhen: {when}\n---\nKeep it small.\n')

    def test_add_of_a_pack_in_the_repo_names_no_ref(self):
        self.project_doc('design', 'Changing the design')

        result = self.sync('add', 'project', '.', '--path', 'docs/agents/project')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'project: added\n')

    def test_resync_after_a_pack_in_the_repo_changes_says_it_changed(self):
        self.project_doc('design', 'Changing the design')
        self.sync('add', 'project', '.', '--path', 'docs/agents/project')
        self.project_doc('billing', 'Editing billing')

        result = self.sync()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'project: changed\n')

    def test_filling_a_pasted_header_block_says_so(self):
        (self.repo / 'AGENTS.md').write_text('# Repo\n\n' + EMPTY_HEADER)

        result = self.sync()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'Updated the header block\n')

    def test_first_sync_says_it_created_agents_md_and_linked_claude_md(self):
        (self.repo / 'AGENTS.md').unlink()
        (self.repo / 'CLAUDE.md').unlink()

        result = self.sync()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'Created AGENTS.md\nLinked CLAUDE.md to AGENTS.md\n')

    def test_sync_that_adds_the_claude_md_link_says_so(self):
        (self.repo / 'CLAUDE.md').unlink()

        result = self.sync()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'Linked CLAUDE.md to AGENTS.md\n')


if __name__ == '__main__':
    unittest.main()
