import shutil
import unittest

from test_cli import SyncCase, git
from test_nested import doc


class ImportPackCase(SyncCase):
    """The house-rules pack imported into the repo's own docs, the project pack, read from the working tree."""

    def setUp(self):
        super().setUp()
        self.ref = self.publish({
            'pack.md': 'Prefer small PRs.\n',
            'testing.md': doc('Writing tests', 'Test behavior.\n'),
        })
        self.docs = self.repo / 'docs' / 'agents' / 'project'
        self.docs.mkdir(parents=True)
        (self.docs / 'design.md').write_text(doc('Changing the design', 'Keep it small.\n'))
        self.agents_md = self.repo / 'AGENTS.md'
        self.import_md = self.docs / 'house-rules' / 'pack.md'
        self.generated = self.repo / 'docs' / 'agents' / 'packs' / 'project' / 'house-rules'
        self.add_project()

    def add_project(self):
        result = self.sync('add', 'project', '.', '--path', 'docs/agents/project')
        self.assertEqual(result.returncode, 0, result.stderr)

    def import_rules(self, *args, name='house-rules', into='docs/agents/project'):
        return self.sync('add', name, str(self.origin), '--path', 'context', '--into', into, *args)

    def front(self, ref=None, when=None):
        return ('---\n' + f'when: {when}\n' * bool(when)
                + f'from: {self.origin}\npath: context\nref: {ref or self.ref}\n---\n')


class ImportTests(ImportPackCase):
    def test_add_into_writes_an_import_pack_pinned_to_the_latest_commit(self):
        result = self.import_rules('--when', 'Reviewing a PR')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.import_md.read_text(), self.front(when='Reviewing a PR'))
        self.assertIn(f'house-rules: added @ {self.ref[:7]}\n', result.stdout)

    def test_import_pack_with_a_when_gets_a_row_in_its_parents_table(self):
        result = self.import_rules('--when', 'Reviewing a PR')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('## project context\n\n| When | Read |\n|---|---|\n'
                      '| Changing the design | `docs/agents/project/design.md` |\n'
                      '| Reviewing a PR | `docs/agents/packs/project/house-rules/pack.md` |\n<!-- context-packs:end',
                      self.agents_md.read_text())
        self.assertEqual((self.generated / 'pack.md').read_text(),
                         'Prefer small PRs.\n\n## house-rules context\n\n| When | Read |\n|---|---|\n'
                         '| Writing tests | `docs/agents/packs/project/house-rules/testing.md` |\n')
        self.assertEqual((self.generated / 'testing.md').read_text(), doc('Writing tests', 'Test behavior.\n'))

    def test_import_pack_without_a_when_is_pasted_after_its_parent(self):
        result = self.import_rules()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('| Changing the design | `docs/agents/project/design.md` |\n\n'
                      'Prefer small PRs.\n\n## house-rules context\n\n| When | Read |\n|---|---|\n'
                      '| Writing tests | `docs/agents/packs/project/house-rules/testing.md` |\n<!-- context-packs:end',
                      self.agents_md.read_text())
        self.assertFalse((self.generated / 'pack.md').exists())

    def test_import_packs_when_replaces_the_imported_packs_own(self):
        self.ref = self.share(doc('Working on anything', 'Prefer small PRs.\n'))

        result = self.import_rules()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('\n\nPrefer small PRs.\n\n## house-rules context', self.agents_md.read_text())
        self.assertNotIn('Working on anything', self.agents_md.read_text())

    def test_rules_written_in_the_import_pack_come_before_the_imported_ones(self):
        self.import_rules()
        self.import_md.write_text(self.front() + 'Small means under 200 lines.\n')

        result = self.sync()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('\n\nSmall means under 200 lines.\n\nPrefer small PRs.\n', self.agents_md.read_text())

    def test_packs_nested_in_the_imported_pack_render_as_written(self):
        self.ref = self.publish({'frontend/pack.md': doc('Editing `web/**`', 'Keep components small.\n')})

        result = self.import_rules('--when', 'Reviewing a PR')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('| Editing `web/**` | `docs/agents/packs/project/house-rules/frontend.md` |\n',
                      (self.generated / 'pack.md').read_text())
        self.assertEqual((self.generated / 'frontend.md').read_text(),
                         'Keep components small.\n')

    def test_import_pack_in_a_nested_pack_renders_into_its_index(self):
        (self.docs / 'review' / 'pack.md').parent.mkdir()
        (self.docs / 'review' / 'pack.md').write_text(doc('Reviewing code', 'Read the tests first.\n'))

        result = self.import_rules(into='docs/agents/project/review')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.repo / 'docs' / 'agents' / 'packs' / 'project' / 'review.md').read_text(),
                         'Read the tests first.\n\nPrefer small PRs.\n\n## house-rules context\n\n'
                         '| When | Read |\n|---|---|\n'
                         '| Writing tests | `docs/agents/packs/project/review/house-rules/testing.md` |\n')

    def test_update_moves_the_import_packs_pin_and_keeps_the_rest_of_it(self):
        self.import_rules('--when', 'Reviewing a PR')
        self.import_md.write_text(self.import_md.read_text() + 'Small means under 200 lines.\n')
        latest = self.share('Prefer small PRs.\nWrite tests first.\n')

        result = self.sync('update')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.import_md.read_text(),
                         self.front(latest, 'Reviewing a PR') + 'Small means under 200 lines.\n')
        self.assertIn('Write tests first.', (self.generated / 'pack.md').read_text())
        self.assertIn(f'house-rules: {self.ref[:7]} → {latest[:7]}\n', result.stdout)

    def test_update_by_name_moves_only_that_import_pack(self):
        self.import_rules()
        latest = self.share('Prefer small PRs.\nWrite tests first.\n')

        result = self.sync('update', 'house-rules')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.import_md.read_text(), self.front(latest))

    def test_resync_keeps_the_import_pack_at_its_pin(self):
        self.import_rules()
        self.share('Prefer small PRs.\nWrite tests first.\n')

        result = self.sync()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('Write tests first.', self.agents_md.read_text())

    def test_resync_with_nothing_to_change_names_the_import_packs_pin(self):
        self.import_rules()

        result = self.sync()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, f'Nothing changed: project, house-rules @ {self.ref[:7]}\n')

    def test_remove_deletes_the_import_pack_and_its_generated_files(self):
        self.import_rules()

        result = self.sync('remove', 'house-rules')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.import_md.parent.exists())
        self.assertFalse(self.generated.exists())
        self.assertNotIn('Prefer small PRs.', self.agents_md.read_text())
        self.assertIn('house-rules: removed\n', result.stdout)

    def test_deleting_the_import_pack_by_hand_clears_its_files_on_resync(self):
        self.import_rules()
        shutil.rmtree(self.import_md.parent)

        result = self.sync()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.generated.exists())

    def test_list_shows_import_packs_under_the_pack_holding_them(self):
        self.import_rules()

        result = self.sync('list')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, f'project  .  docs/agents/project\n'
                                        f'  house-rules  {self.origin}  context @ {self.ref}\n')

    def test_editing_an_imported_doc_stops_the_next_sync(self):
        self.import_rules('--when', 'Reviewing a PR')
        (self.generated / 'testing.md').write_text('Edited here.\n')

        result = self.sync()

        self.assertEqual(result.returncode, 1)
        self.assertIn('project', result.stderr)
        self.assertEqual((self.generated / 'testing.md').read_text(), 'Edited here.\n')


class ImportRuleTests(ImportPackCase):
    """What stops a sync with import packs."""

    def test_into_a_folder_outside_any_pack_read_from_disk_stops(self):
        result = self.import_rules(into='docs/agents/elsewhere')

        self.assertEqual(result.returncode, 1)
        self.assertIn('docs/agents/elsewhere', result.stderr)
        self.assertFalse((self.repo / 'docs' / 'agents' / 'elsewhere').exists())

    def test_when_without_into_stops(self):
        result = self.add('--when', 'Reviewing a PR')

        self.assertEqual(result.returncode, 1)
        self.assertIn('--into', result.stderr)

    def test_into_a_folder_that_already_has_the_import_packs_folder_stops(self):
        (self.docs / 'house-rules').mkdir()

        result = self.import_rules()

        self.assertEqual(result.returncode, 1)
        self.assertIn('docs/agents/project/house-rules', result.stderr)
        self.assertFalse(self.import_md.exists())

    def test_import_pack_named_like_a_pack_in_agents_md_stops(self):
        self.add()
        before = self.agents_md.read_text()

        result = self.import_rules(name='house-rules')

        self.assertEqual(result.returncode, 1)
        self.assertIn('house-rules', result.stderr)
        self.assertFalse(self.import_md.exists())
        self.assertEqual(self.agents_md.read_text(), before)

    def test_two_import_packs_with_one_name_stop(self):
        self.import_rules()
        (self.docs / 'review' / 'house-rules').mkdir(parents=True)
        shutil.copy(self.import_md, self.docs / 'review' / 'house-rules' / 'pack.md')

        result = self.sync()

        self.assertEqual(result.returncode, 1)
        self.assertIn('house-rules', result.stderr)

    def test_import_pack_overlapping_a_pack_in_agents_md_stops(self):
        self.sync('add', 'shared', str(self.origin), '--path', 'context')

        result = self.import_rules()

        self.assertEqual(result.returncode, 1)
        self.assertIn('overlap', result.stderr)
        self.assertFalse(self.import_md.exists())

    def test_import_pack_holding_another_file_stops(self):
        self.import_rules()
        (self.import_md.parent / 'notes.md').write_text(doc('Taking notes'))

        result = self.sync()

        self.assertEqual(result.returncode, 1)
        self.assertIn('docs/agents/project/house-rules', result.stderr)

    def test_import_pack_from_a_git_url_without_a_ref_stops(self):
        self.import_md.parent.mkdir()
        self.import_md.write_text(f'---\nfrom: {self.origin}\npath: context\n---\n')

        result = self.sync()

        self.assertEqual(result.returncode, 1)
        self.assertIn('docs/agents/project/house-rules/pack.md', result.stderr)
        self.assertIn('ref', result.stderr)

    def test_fetched_pack_holding_an_import_pack_stops(self):
        other_origin, other = self.remote('other-rules')
        self.publish({'pack.md': 'Use tabs.\n'}, checkout=other)
        self.publish({'other/pack.md': f'---\nfrom: {other_origin}\npath: context\nref: '
                                       f'{git(other, "rev-parse", "HEAD")}\n---\n'})

        result = self.add()

        self.assertEqual(result.returncode, 1)
        self.assertIn('context/other/pack.md', result.stderr)
        self.assertIn('only a pack read from a folder on disk', result.stderr)


if __name__ == '__main__':
    unittest.main()
