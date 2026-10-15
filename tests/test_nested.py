import unittest

from test_cli import SyncCase, block, doc, packed


class FolderTests(SyncCase):
    """A folder without a pack.md, which only groups files: its docs join the nearest pack's table."""

    def setUp(self):
        super().setUp()
        self.publish({
            'pack.md': 'Prefer small PRs.\n',
            'typescript/react.md': doc('Writing React components', 'Use function components.\n'),
            'typescript/types.md': doc('Declaring types', 'Prefer unions.\n'),
            'typescript/example.tsx': 'export const x = 1;\n',
        })
        self.synced = self.gen / 'house-rules'

    def test_folder_docs_join_the_packs_table(self):
        result = self.add()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.agents(),
                         block(packed('house-rules', 'Prefer small PRs.\n\n## house-rules context\n\n'
                                      '| When | Read |\n|---|---|\n'
                                      '| Writing React components | `context-packs/gen/house-rules/typescript/react.md` |\n'
                                      '| Declaring types | `context-packs/gen/house-rules/typescript/types.md` |\n')))

    def test_every_file_in_the_folder_is_copied(self):
        result = self.add()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(sorted(p.name for p in (self.synced / 'typescript').iterdir()),
                         ['example.tsx', 'react.md', 'types.md'])
        self.assertEqual((self.synced / 'typescript' / 'example.tsx').read_text(), 'export const x = 1;\n')


class NestedPackTests(SyncCase):
    """A folder with a pack.md inside the installed pack, which gets a row pointing at a generated index."""

    def setUp(self):
        super().setUp()
        self.publish({
            'pack.md': 'Prefer small PRs.\n',
            'testing.md': doc('Writing tests', 'Test behavior.\n'),
            'frontend/pack.md': doc('Editing `web/**`', 'Keep components small.\n'),
            'frontend/react.md': doc('Writing React components', 'Use function components.\n'),
            'frontend/css/layout.md': doc('Laying out pages', 'Use grid.\n'),
        })
        self.synced = self.gen / 'house-rules'

    def test_nested_pack_gets_a_row_in_its_parents_table(self):
        result = self.add()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.agents(),
                         block(packed('house-rules', 'Prefer small PRs.\n\n## house-rules context\n\n'
                                                     '| When | Read |\n|---|---|\n'
                                                     '| Editing `web/**` | `context-packs/gen/house-rules/frontend.md` |\n'
                                                     '| Writing tests | `context-packs/gen/house-rules/testing.md` |\n')))

    def test_nested_pack_whose_when_is_always_is_inlined_after_its_parent_between_markers(self):
        self.publish({'frontend/pack.md': doc('always', 'Keep components small.\n')})

        result = self.add()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('| Writing tests | `context-packs/gen/house-rules/testing.md` |\n\n'
                      '<!-- context-packs:pack house-rules/frontend -->\nKeep components small.\n\n'
                      '## house-rules/frontend context\n\n| When | Read |\n|---|---|\n'
                      '| Laying out pages | `context-packs/gen/house-rules/frontend/css/layout.md` |\n'
                      '| Writing React components | `context-packs/gen/house-rules/frontend/react.md` |\n'
                      '<!-- context-packs:pack-end house-rules/frontend -->\n'
                      '<!-- context-packs:pack-end house-rules -->\n', self.agents())
        self.assertFalse((self.synced / 'frontend.md').exists())
        self.assertTrue((self.synced / 'frontend' / 'react.md').exists())

    def test_nested_packs_index_holds_its_rules_and_table_without_front_matter(self):
        result = self.add()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.synced / 'frontend.md').read_text(),
                         'Keep components small.\n\n## house-rules/frontend context\n\n| When | Read |\n|---|---|\n'
                         '| Laying out pages | `context-packs/gen/house-rules/frontend/css/layout.md` |\n'
                         '| Writing React components | `context-packs/gen/house-rules/frontend/react.md` |\n')

    def test_nested_packs_files_are_copied_without_its_pack_md(self):
        result = self.add()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(sorted(p.relative_to(self.synced).as_posix() for p in self.synced.rglob('*') if p.is_file()),
                         ['frontend.md', 'frontend/css/layout.md', 'frontend/react.md', 'testing.md'])

    def test_generated_index_edited_in_the_repo_stops_the_sync(self):
        self.add()
        index = self.synced / 'frontend.md'
        index.write_text('Edited here.\n')

        result = self.sync()

        self.assertEqual(result.returncode, 1)
        self.assertIn('context-packs/gen', result.stderr)
        self.assertEqual(index.read_text(), 'Edited here.\n')

    def test_nested_pack_without_a_when_line_stops_the_sync(self):
        self.publish({'backend/pack.md': 'Use Rails.\n'})

        result = self.add()

        self.assertEqual(result.returncode, 1)
        self.assertIn('context/backend/pack.md', result.stderr)
        self.assertFalse(self.agents_md.exists())

    def test_doc_without_a_when_line_stops_the_sync(self):
        self.publish({'frontend/css/grid.md': 'Use grid.\n'})

        result = self.add()

        self.assertEqual(result.returncode, 1)
        self.assertIn('context/frontend/css/grid.md', result.stderr)
        self.assertFalse(self.agents_md.exists())

    def test_doc_whose_when_is_always_stops_the_sync(self):
        self.publish({'testing.md': doc('always', 'Test behavior.\n')})

        result = self.add()

        self.assertEqual(result.returncode, 1)
        self.assertIn('context/testing.md', result.stderr)
        self.assertIn('pack.md', result.stderr)
        self.assertFalse(self.agents_md.exists())

    def test_tier_on_a_doc_stops_the_sync(self):
        self.publish({'testing.md': doc('Writing tests', tier='required')})

        result = self.add()

        self.assertEqual(result.returncode, 1)
        self.assertIn('context/testing.md', result.stderr)
        self.assertIn('tier', result.stderr)

    def test_stray_file_in_the_synced_folder_stops_the_sync(self):
        self.add()
        (self.synced / '.DS_Store').write_text('')

        result = self.sync()

        self.assertEqual(result.returncode, 1)
        self.assertIn('a file in context-packs/gen was edited', result.stderr)
        self.assertTrue((self.synced / '.DS_Store').exists())

    def test_nested_pack_beside_a_doc_of_the_same_name_stops_the_sync(self):
        self.publish({'frontend.md': doc('Editing the frontend')})

        result = self.add()

        self.assertEqual(result.returncode, 1)
        self.assertIn('frontend', result.stderr)
        self.assertFalse(self.agents_md.exists())


class OverlapTests(SyncCase):
    """A pack and a folder inside it installed from the same origin."""

    def setUp(self):
        super().setUp()
        self.publish({
            'pack.md': 'Prefer small PRs.\n',
            'typescript/pack.md': doc('Editing `**/*.ts`', 'Prefer unions.\n'),
        })

    def add_typescript(self, origin=None):
        return self.sync('add', 'typescript', str(origin or self.origin), '--path', 'context/typescript')

    def test_adding_a_folder_inside_an_installed_pack_stops_untouched(self):
        self.add()
        before = self.agents_md.read_text()

        result = self.add_typescript()

        self.assertEqual(result.returncode, 1)
        self.assertIn('overlap', result.stderr)
        self.assertIn('house-rules', result.stderr)
        self.assertIn('typescript', result.stderr)
        self.assertEqual(self.agents_md.read_text(), before)
        self.assertFalse(self.import_md('typescript').parent.exists())

    def test_adding_a_pack_around_an_installed_one_stops_untouched(self):
        self.add_typescript()
        before = self.agents_md.read_text()

        result = self.add()

        self.assertEqual(result.returncode, 1)
        self.assertIn('overlap', result.stderr)
        self.assertEqual(self.agents_md.read_text(), before)

    def test_same_folder_from_another_origin_doesnt_overlap(self):
        other_origin, other = self.remote('other-rules')
        self.publish({'typescript/pack.md': doc('Editing `**/*.ts`', 'Use strict mode.\n')}, checkout=other)
        self.add()

        result = self.add_typescript(other_origin)

        self.assertEqual(result.returncode, 0, result.stderr)


class InstallPointTests(SyncCase):
    """A folder with a pack.md installed on its own, which renders the way it would inside its parent."""

    def setUp(self):
        super().setUp()
        self.publish({
            'pack.md': 'Prefer small PRs.\n',
            'typescript/pack.md': doc('Editing `**/*.ts`', 'Prefer unions.\n'),
            'typescript/types.md': doc('Declaring types'),
        })
        self.synced = self.gen / 'typescript'

    def add_folder(self, name):
        return self.sync('add', name, str(self.origin), '--path', f'context/{name}')

    def test_pack_with_a_when_line_gets_a_row_in_the_context_table(self):
        result = self.add_folder('typescript')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.agents(),
                         block('## Context\n\n| When | Read |\n|---|---|\n'
                               '| Editing `**/*.ts` | `context-packs/gen/typescript/pack.md` |\n'))

    def test_pack_with_a_when_line_gets_an_index_of_its_rules_and_table(self):
        result = self.add_folder('typescript')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.synced / 'pack.md').read_text(),
                         'Prefer unions.\n\n## typescript context\n\n| When | Read |\n|---|---|\n'
                         '| Declaring types | `context-packs/gen/typescript/types.md` |\n')

    def test_nested_pack_named_pack_beside_a_root_index_stops_the_sync(self):
        self.publish({'typescript/pack/pack.md': doc('Packaging')})

        result = self.add_folder('typescript')

        self.assertEqual(result.returncode, 1)
        self.assertIn('context/typescript/pack', result.stderr)
        self.assertFalse(self.agents_md.exists())


class LocalNestedPackTests(SyncCase):
    """A nested pack in the repo's own context-packs/: its docs stay where they are, and only its index is
    generated."""

    def setUp(self):
        super().setUp()
        self.write('context-packs/project/design.md', doc('Changing the design', 'Keep it small.\n'))
        self.write('context-packs/project/deploy/pack.md', doc('Deploying', 'Ship on green.\n'))
        self.write('context-packs/project/deploy/rollback.md', doc('Rolling back', 'Revert first.\n'))
        self.index = self.gen / 'project' / 'deploy.md'

    def test_nested_packs_index_is_generated_and_its_docs_stay_where_they_are(self):
        result = self.sync()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.agents(),
                         block('## Context\n\n| When | Read |\n|---|---|\n'
                               '| Deploying | `context-packs/gen/project/deploy.md` |\n'
                               '| Changing the design | `context-packs/project/design.md` |\n'))
        self.assertEqual(self.index.read_text(),
                         'Ship on green.\n\n## project/deploy context\n\n| When | Read |\n|---|---|\n'
                         '| Rolling back | `context-packs/project/deploy/rollback.md` |\n')
        self.assertEqual(sorted(p.name for p in self.index.parent.iterdir()), ['deploy.md'])

    def test_generated_index_edited_in_the_repo_stops_the_sync(self):
        self.sync()
        self.index.write_text('Edited here.\n')

        result = self.sync()

        self.assertEqual(result.returncode, 1)
        self.assertIn('context-packs/gen', result.stderr)
        self.assertEqual(self.index.read_text(), 'Edited here.\n')

    def test_editing_a_nested_packs_rules_regenerates_its_index_on_resync(self):
        self.sync()
        self.write('context-packs/project/deploy/pack.md', doc('Deploying', 'Ship on green, never on Friday.\n'))

        result = self.sync()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.index.read_text().startswith('Ship on green, never on Friday.\n'))


if __name__ == '__main__':
    unittest.main()
