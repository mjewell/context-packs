import shutil
import unittest

from test_cli import HEADER, SyncCase, block, doc, git


class ImportPackCase(SyncCase):
    """The house-rules pack imported into a folder of the repo's own docs, context-packs/project/."""

    def setUp(self):
        super().setUp()
        self.ref = self.publish({
            'pack.md': 'Prefer small PRs.\n',
            'testing.md': doc('Writing tests', 'Test behavior.\n'),
        })
        self.write('context-packs/project/design.md', doc('Changing the design', 'Keep it small.\n'))
        self.id = 'project/house-rules'
        self.generated = self.gen / 'project' / 'house-rules'

    def import_rules(self, *args, id='project/house-rules'):
        return self.add(*args, id=id)


class ImportTests(ImportPackCase):
    def test_add_at_a_nested_id_writes_an_import_pack_pinned_to_the_latest_commit(self):
        result = self.import_rules('--when', 'Reviewing a PR')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.import_md(self.id).read_text(), self.front(self.ref, 'Reviewing a PR'))
        self.assertIn(f'project/house-rules: added @ {self.ref[:7]}\n', result.stdout)

    def test_import_pack_with_a_when_gets_a_row_in_its_parents_table(self):
        result = self.import_rules('--when', 'Reviewing a PR')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.agents(),
                         block('## Context\n\n| When | Read |\n|---|---|\n'
                               '| Changing the design | `context-packs/project/design.md` |\n'
                               '| Reviewing a PR | `context-packs/gen/project/house-rules/pack.md` |\n'))
        self.assertEqual((self.generated / 'pack.md').read_text(),
                         'Prefer small PRs.\n\n## project/house-rules context\n\n| When | Read |\n|---|---|\n'
                         '| Writing tests | `context-packs/gen/project/house-rules/testing.md` |\n')
        self.assertEqual((self.generated / 'testing.md').read_text(), doc('Writing tests', 'Test behavior.\n'))

    def test_import_pack_without_a_when_is_inlined_after_its_parent(self):
        result = self.import_rules()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.agents(),
                         block('## Context\n\n| When | Read |\n|---|---|\n'
                               '| Changing the design | `context-packs/project/design.md` |\n\n'
                               'Prefer small PRs.\n\n## project/house-rules context\n\n| When | Read |\n|---|---|\n'
                               '| Writing tests | `context-packs/gen/project/house-rules/testing.md` |\n'))
        self.assertFalse((self.generated / 'pack.md').exists())

    def test_import_pack_without_a_when_follows_its_authors(self):
        self.ref = self.share(doc('Working on anything', 'Prefer small PRs.\n'))

        result = self.import_rules()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('| Working on anything | `context-packs/gen/project/house-rules/pack.md` |\n', self.agents())

    def test_import_packs_when_replaces_its_authors(self):
        self.ref = self.share(doc('Working on anything', 'Prefer small PRs.\n'))

        result = self.import_rules('--when', 'Reviewing a PR')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('| Reviewing a PR | `context-packs/gen/project/house-rules/pack.md` |\n', self.agents())
        self.assertNotIn('Working on anything', self.agents())

    def test_when_always_inlines_the_pack_even_with_its_authors_when(self):
        self.ref = self.share(doc('Working on anything', 'Prefer small PRs.\n'))

        result = self.import_rules('--when', 'always')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('\n\nPrefer small PRs.\n\n## project/house-rules context', self.agents())
        self.assertNotIn('Working on anything', self.agents())

    def test_rules_written_in_the_import_pack_come_before_the_imported_ones(self):
        self.import_rules()
        self.import_md(self.id).write_text(self.front(self.ref) + 'Small means under 200 lines.\n')

        result = self.sync()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('\n\nSmall means under 200 lines.\n\nPrefer small PRs.\n', self.agents())

    def test_packs_nested_in_the_imported_pack_render_as_written(self):
        self.ref = self.publish({'frontend/pack.md': doc('Editing `web/**`', 'Keep components small.\n')})

        result = self.import_rules('--when', 'Reviewing a PR')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('| Editing `web/**` | `context-packs/gen/project/house-rules/frontend.md` |\n',
                      (self.generated / 'pack.md').read_text())
        self.assertEqual((self.generated / 'frontend.md').read_text(), 'Keep components small.\n')

    def test_import_pack_in_a_nested_pack_renders_into_its_index(self):
        self.write('context-packs/project/review/pack.md', doc('Reviewing code', 'Read the tests first.\n'))

        result = self.import_rules(id='project/review/house-rules')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.gen / 'project' / 'review.md').read_text(),
                         'Read the tests first.\n\nPrefer small PRs.\n\n## project/review/house-rules context\n\n'
                         '| When | Read |\n|---|---|\n'
                         '| Writing tests | `context-packs/gen/project/review/house-rules/testing.md` |\n')

    def test_import_pack_moved_to_another_folder_renders_there_on_resync(self):
        self.import_rules()
        self.write('context-packs/project/review/pack.md', doc('Reviewing code', 'Read the tests first.\n'))
        shutil.move(str(self.import_md(self.id).parent), str(self.packs / 'project' / 'review' / 'house-rules'))

        result = self.sync()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('Prefer small PRs.', self.agents())
        self.assertIn('Read the tests first.\n\nPrefer small PRs.\n', (self.gen / 'project' / 'review.md').read_text())
        self.assertFalse(self.generated.exists())

    def test_update_moves_the_import_packs_pin_and_keeps_the_rest_of_it(self):
        self.import_rules('--when', 'Reviewing a PR')
        self.import_md(self.id).write_text(self.import_md(self.id).read_text() + 'Small means under 200 lines.\n')
        latest = self.share('Prefer small PRs.\nWrite tests first.\n')

        result = self.sync('update')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.import_md(self.id).read_text(),
                         self.front(latest, 'Reviewing a PR') + 'Small means under 200 lines.\n')
        self.assertIn('Write tests first.', (self.generated / 'pack.md').read_text())
        self.assertEqual(result.stdout, f'project/house-rules: {self.ref[:7]} → {latest[:7]}\n')

    def test_update_by_id_moves_only_that_import_pack(self):
        self.import_rules()
        latest = self.share('Prefer small PRs.\nWrite tests first.\n')

        result = self.sync('update', 'project/house-rules')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.import_md(self.id).read_text(), self.front(latest))

    def test_resync_keeps_the_import_pack_at_its_pin(self):
        self.import_rules()
        self.share('Prefer small PRs.\nWrite tests first.\n')

        result = self.sync()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('Write tests first.', self.agents())

    def test_resync_with_nothing_to_change_names_the_import_packs_pin(self):
        self.import_rules()

        result = self.sync()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, f'Nothing changed: project/house-rules @ {self.ref[:7]}\n')

    def test_remove_deletes_the_import_pack_and_its_generated_files(self):
        self.import_rules()

        result = self.sync('remove', 'project/house-rules')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.import_md(self.id).parent.exists())
        self.assertFalse(self.generated.exists())
        self.assertTrue((self.packs / 'project' / 'design.md').exists())
        self.assertNotIn('Prefer small PRs.', self.agents())
        self.assertEqual(result.stdout, 'project/house-rules: removed\n')

    def test_deleting_the_import_pack_by_hand_clears_its_files_on_resync(self):
        self.import_rules()
        shutil.rmtree(self.import_md(self.id).parent)

        result = self.sync()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.gen.exists())

    def test_list_shows_import_packs_by_id(self):
        self.import_rules()

        result = self.sync('list')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, f'project/house-rules  {self.origin}  context @ {self.ref}\n')

    def test_editing_an_imported_doc_stops_the_next_sync(self):
        self.import_rules('--when', 'Reviewing a PR')
        (self.generated / 'testing.md').write_text('Edited here.\n')

        result = self.sync()

        self.assertEqual(result.returncode, 1)
        self.assertIn('context-packs/gen', result.stderr)
        self.assertEqual((self.generated / 'testing.md').read_text(), 'Edited here.\n')


class ImportRuleTests(ImportPackCase):
    """What stops a sync with import packs."""

    def test_two_import_packs_of_one_folder_stop(self):
        self.import_rules()

        result = self.import_rules(id='shared')

        self.assertEqual(result.returncode, 1)
        self.assertIn('overlap', result.stderr)
        self.assertFalse(self.import_md('shared').exists())

    def test_import_pack_holding_another_file_stops(self):
        self.import_rules()
        self.write(f'context-packs/{self.id}/notes.md', doc('Taking notes'))

        result = self.sync()

        self.assertEqual(result.returncode, 1)
        self.assertIn('context-packs/project/house-rules', result.stderr)
        self.assertIn('notes.md', result.stderr)

    def test_add_inside_an_import_packs_folder_stops_untouched(self):
        self.import_rules()
        before = self.agents_md.read_text()
        other_origin, other = self.remote('other-rules')
        self.publish({'pack.md': 'Use tabs.\n'}, checkout=other)

        result = self.sync('add', f'{self.id}/other', str(other_origin), '--path', 'context')

        self.assertEqual(result.returncode, 1)
        self.assertIn('context-packs/project/house-rules', result.stderr)
        self.assertFalse(self.import_md(f'{self.id}/other').parent.exists())
        self.assertEqual(self.agents_md.read_text(), before)

    def test_fetched_pack_holding_an_import_pack_from_git_stops(self):
        other_origin, other = self.remote('other-rules')
        self.publish({'pack.md': 'Use tabs.\n'}, checkout=other)
        self.publish({'other/pack.md': f'---\nfrom: {other_origin}\npath: context\nref: '
                                       f'{git(other, "rev-parse", "HEAD")}\n---\n'})

        result = self.import_rules()

        self.assertEqual(result.returncode, 1)
        self.assertIn('context/other/pack.md', result.stderr)
        self.assertIn('from git', result.stderr)
        self.assertFalse(self.import_md(self.id).parent.exists())

    def test_import_pack_of_a_folder_holding_context_packs_stops_untouched(self):
        result = self.sync('add', 'self', '.')

        self.assertEqual(result.returncode, 1)
        self.assertIn('overlap', result.stderr)
        self.assertFalse(self.import_md('self').parent.exists())

    def test_import_pack_of_a_folder_inside_context_packs_stops_untouched(self):
        result = self.sync('add', 'loop', 'context-packs/project')

        self.assertEqual(result.returncode, 1)
        self.assertIn('overlap', result.stderr)
        self.assertFalse(self.import_md('loop').parent.exists())


class LocalImportTests(SyncCase):
    """An import pack whose from is a path, inside a pack from elsewhere: the path is in that pack's origin, so a
    pack can point at another folder of its own repo, and works the same wherever it's installed."""

    def setUp(self):
        super().setUp()
        self.ref = self.publish({'pack.md': 'Prefer small PRs.\n', 'common/pack.md': '---\nfrom: .\npath: common\n---\n'})
        self.publish({'pack.md': 'Use tabs.\n', 'style.md': doc('Styling code', 'Indent once.\n')}, folder='common')
        self.ref = git(self.source, 'rev-parse', 'HEAD')

    def test_local_import_in_a_pack_from_git_reads_its_origin_at_the_packs_ref(self):
        result = self.add()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.agents(),
                         block('Prefer small PRs.\n\nUse tabs.\n\n## house-rules/common context\n\n'
                               '| When | Read |\n|---|---|\n'
                               '| Styling code | `context-packs/gen/house-rules/common/style.md` |\n'))
        self.assertEqual((self.gen / 'house-rules' / 'common' / 'style.md').read_text(),
                         doc('Styling code', 'Indent once.\n'))

    def test_local_import_in_a_pack_from_git_moves_only_with_its_pin(self):
        self.add()
        self.publish({'pack.md': 'Use spaces.\n'}, folder='common')

        resynced = self.sync()
        self.assertEqual(resynced.returncode, 0, resynced.stderr)
        self.assertIn('Use tabs.\n', self.agents())

        updated = self.sync('update')
        self.assertEqual(updated.returncode, 0, updated.stderr)
        self.assertIn('Use spaces.\n', self.agents())

    def test_local_import_reaching_outside_its_origin_stops(self):
        self.publish({'common/pack.md': '---\nfrom: ..\npath: elsewhere\n---\n'})

        result = self.add()

        self.assertEqual(result.returncode, 1)
        self.assertIn('context/common/pack.md', result.stderr)
        self.assertIn('outside', result.stderr)

    def test_local_import_of_a_folder_holding_its_pack_stops(self):
        self.publish({'common/pack.md': '---\nfrom: .\n---\n'})

        result = self.add()

        self.assertEqual(result.returncode, 1)
        self.assertIn('overlap', result.stderr)

    def test_local_import_in_a_folder_on_disk_reads_that_folder_where_it_is(self):
        result = self.sync('add', 'house-rules', '../house-rules', '--path', 'context')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(HEADER + '\nPrefer small PRs.\n\nUse tabs.\n\n## house-rules/common context\n\n'
                      '| When | Read |\n|---|---|\n| Styling code | `../house-rules/common/style.md` |\n',
                      self.agents())
        self.assertFalse(self.gen.exists())


if __name__ == '__main__':
    unittest.main()
