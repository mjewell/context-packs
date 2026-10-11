import unittest

from test_cli import SyncCase, git


def doc(when, text='', **fields):
    front = ''.join(f'{key}: {value}\n' for key, value in fields.items())
    return f'---\nwhen: {when}\n{front}---\n{text}'


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
        self.synced = self.repo / 'docs' / 'agents' / 'packs' / 'house-rules'

    def test_folder_docs_join_the_packs_table(self):
        result = self.add()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(self.start() + 'Prefer small PRs.\n\n## house-rules context\n\n| When | Read |\n|---|---|\n'
                      '| Writing React components | `docs/agents/packs/house-rules/typescript/react.md` |\n'
                      '| Declaring types | `docs/agents/packs/house-rules/typescript/types.md` |\n'
                      '<!-- context-packs:end',
                      (self.repo / 'AGENTS.md').read_text())

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
        self.synced = self.repo / 'docs' / 'agents' / 'packs' / 'house-rules'
        self.agents_md = self.repo / 'AGENTS.md'

    def test_nested_pack_gets_a_row_in_its_parents_table(self):
        result = self.add()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Prefer small PRs.\n\n## house-rules context\n\n| When | Read |\n|---|---|\n'
                      '| Editing `web/**` | `docs/agents/packs/house-rules/frontend.md` |\n'
                      '| Writing tests | `docs/agents/packs/house-rules/testing.md` |\n'
                      '<!-- context-packs:end',
                      self.agents_md.read_text())

    def test_nested_packs_index_holds_its_rules_and_table_without_front_matter(self):
        result = self.add()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.synced / 'frontend.md').read_text(),
                         'Keep components small.\n\n## house-rules/frontend context\n\n| When | Read |\n|---|---|\n'
                         '| Laying out pages | `docs/agents/packs/house-rules/frontend/css/layout.md` |\n'
                         '| Writing React components | `docs/agents/packs/house-rules/frontend/react.md` |\n')

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
        self.assertIn('docs/agents/packs/house-rules', result.stderr)
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

    def test_tier_on_a_doc_stops_the_sync(self):
        self.publish({'testing.md': doc('Writing tests', tier='required')})

        result = self.add()

        self.assertEqual(result.returncode, 1)
        self.assertIn('context/testing.md', result.stderr)
        self.assertIn('tier', result.stderr)

    def test_optional_other_than_true_stops_the_sync(self):
        self.publish({'frontend/pack.md': doc('Editing `web/**`', optional='false')})

        result = self.add()

        self.assertEqual(result.returncode, 1)
        self.assertIn('context/frontend/pack.md', result.stderr)
        self.assertFalse(self.agents_md.exists())

    def test_stray_file_in_the_synced_folder_stops_the_sync(self):
        self.add()
        (self.synced / '.DS_Store').write_text('')

        result = self.sync()

        self.assertEqual(result.returncode, 1)
        self.assertIn('a doc in docs/agents/packs/house-rules was edited', result.stderr)
        self.assertTrue((self.synced / '.DS_Store').exists())

    def test_nested_pack_beside_a_doc_of_the_same_name_stops_the_sync(self):
        self.publish({'frontend.md': doc('Editing the frontend')})

        result = self.add()

        self.assertEqual(result.returncode, 1)
        self.assertIn('frontend', result.stderr)
        self.assertFalse(self.agents_md.exists())


class PickTests(SyncCase):
    """Nested packs marked optional: true, which a repo picks with --docs or the docs command."""

    def setUp(self):
        super().setUp()
        self.publish({
            'pack.md': 'Prefer small PRs.\n',
            'testing.md': doc('Writing tests', 'Test behavior.\n'),
            'skills/pack.md': doc('Editing `**/SKILL.md`', 'Keep skills short.\n', optional='true'),
            'typescript/pack.md': doc('Editing `**/*.ts`', 'Prefer unions.\n', optional='true'),
            'typescript/types.md': doc('Declaring types'),
            'typescript/lint/pack.md': doc('Configuring ESLint', 'Lint in CI.\n'),
            'typescript/react/pack.md': doc('Writing React components', 'Use hooks.\n', optional='true'),
        })
        self.synced = self.repo / 'docs' / 'agents' / 'packs' / 'house-rules'
        self.agents_md = self.repo / 'AGENTS.md'

    def installed(self):
        return sorted(p.relative_to(self.synced).as_posix() for p in self.synced.rglob('*') if p.is_file())

    def test_optional_nested_pack_is_left_out_unless_picked(self):
        result = self.add()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.installed(), ['testing.md'])
        self.assertNotIn('skills', self.agents_md.read_text())

    def test_picked_nested_pack_gets_its_row_and_index(self):
        result = self.add('--docs', 'skills')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.installed(), ['skills.md', 'testing.md'])
        self.assertIn('| Editing `**/SKILL.md` | `docs/agents/packs/house-rules/skills.md` |\n',
                      self.agents_md.read_text())

    def test_picked_pack_brings_its_children_but_not_its_optional_ones(self):
        result = self.add('--docs', 'typescript')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.installed(), ['testing.md', 'typescript.md', 'typescript/lint.md', 'typescript/types.md'])

    def test_picking_a_deeper_pack_pulls_in_the_packs_above_it(self):
        result = self.add('--docs', 'typescript/react')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.installed(), ['testing.md', 'typescript.md', 'typescript/lint.md',
                                            'typescript/react.md', 'typescript/types.md'])
        self.assertIn(' docs=typescript/react -->', self.agents_md.read_text())

    def test_packs_left_out_of_the_choice_are_removed(self):
        self.add('--docs', 'skills,typescript')

        result = self.sync('docs', 'house-rules', 'skills')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.installed(), ['skills.md', 'testing.md'])
        self.assertNotIn('typescript', self.agents_md.read_text())

    def test_unknown_pick_stops_the_sync_and_names_the_nested_packs(self):
        result = self.add('--docs', 'python')

        self.assertEqual(result.returncode, 1)
        self.assertIn('python', result.stderr)
        self.assertIn('skills, typescript, typescript/lint, typescript/react', result.stderr)
        self.assertFalse(self.agents_md.exists())

    def test_picked_pack_gone_from_the_origin_stops_the_update(self):
        self.add('--docs', 'skills')
        self.publish({'skills': None})

        result = self.sync('update')

        self.assertEqual(result.returncode, 1)
        self.assertIn('skills', result.stderr)
        self.assertTrue((self.synced / 'skills.md').exists())

    def test_list_shows_the_nested_packs_as_a_tree_and_why_each_is_installed(self):
        self.add('--docs', 'skills,typescript/react')

        result = self.sync('list')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout,
                         f'house-rules  {self.origin}  context @ {git(self.source, "rev-parse", "HEAD")}\n'
                         '  [x] skills: Editing `**/SKILL.md`\n'
                         '  [x] typescript (needed by typescript/react): Editing `**/*.ts`\n'
                         '    [x] typescript/lint: Configuring ESLint\n'
                         '    [x] typescript/react: Writing React components\n')

    def test_list_leaves_a_pack_unmarked_when_its_parent_isnt_installed(self):
        self.add()

        result = self.sync('list')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.endswith('  [ ] typescript: Editing `**/*.ts`\n'
                                               '    [ ] typescript/lint: Configuring ESLint\n'
                                               '    [ ] typescript/react: Writing React components\n'),
                        result.stdout)

    def test_update_keeps_the_picks_and_updates_them(self):
        self.add('--docs', 'skills')
        self.publish({'skills/pack.md': doc('Editing `**/SKILL.md`', 'Keep skills shorter.\n')})

        result = self.sync('update')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.installed(), ['skills.md', 'testing.md'])
        self.assertTrue((self.synced / 'skills.md').read_text().startswith('Keep skills shorter.\n'))

    def test_picking_nothing_removes_the_nested_packs(self):
        self.add('--docs', 'skills')

        result = self.sync('docs', 'house-rules', '')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.installed(), ['testing.md'])
        self.assertNotIn('docs=', self.agents_md.read_text())

    def test_picking_a_doc_stops_the_sync(self):
        result = self.add('--docs', 'testing')

        self.assertEqual(result.returncode, 1)
        self.assertIn('testing', result.stderr)


class InlineTests(SyncCase):
    """A nested pack with inline: true, whose rules and table follow its parent's instead of taking a row."""

    def setUp(self):
        super().setUp()
        self.publish({
            'pack.md': 'Prefer small PRs.\n',
            'testing.md': doc('Writing tests'),
            'typescript/pack.md': doc('Working in a TypeScript repo', 'Prefer unions.\n', optional='true',
                                      inline='true'),
            'typescript/types.md': doc('Declaring types'),
            'typescript/react/pack.md': doc('Writing React components', 'Use hooks.\n'),
        })
        self.synced = self.repo / 'docs' / 'agents' / 'packs' / 'house-rules'
        self.agents_md = self.repo / 'AGENTS.md'

    def test_picked_inline_pack_follows_its_parent_in_the_block(self):
        result = self.add('--docs', 'typescript')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(self.start().replace(' -->', ' docs=typescript -->') + 'Prefer small PRs.\n\n'
                      '## house-rules context\n\n| When | Read |\n|---|---|\n'
                      '| Writing tests | `docs/agents/packs/house-rules/testing.md` |\n\n'
                      'Prefer unions.\n\n## house-rules/typescript context\n\n| When | Read |\n|---|---|\n'
                      '| Writing React components | `docs/agents/packs/house-rules/typescript/react.md` |\n'
                      '| Declaring types | `docs/agents/packs/house-rules/typescript/types.md` |\n'
                      '<!-- context-packs:end',
                      self.agents_md.read_text())

    def test_inline_pack_gets_no_index_of_its_own(self):
        result = self.add('--docs', 'typescript')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(sorted(p.relative_to(self.synced).as_posix() for p in self.synced.rglob('*') if p.is_file()),
                         ['testing.md', 'typescript/react.md', 'typescript/types.md'])

    def test_inline_pack_left_unpicked_adds_nothing(self):
        result = self.add()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('unions', self.agents_md.read_text())

    def test_inline_pack_that_isnt_optional_needs_no_when_line(self):
        self.publish({'style/pack.md': '---\ninline: true\n---\nUse tabs.\n'})

        result = self.add()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Use tabs.\n', self.agents_md.read_text())

    def test_list_shows_an_inline_pack_without_a_when_line(self):
        self.publish({'style/pack.md': '---\ninline: true\n---\nUse tabs.\n'})
        self.add()

        result = self.sync('list')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('  [x] style\n', result.stdout)

    def test_inline_other_than_true_stops_the_sync(self):
        self.publish({'typescript/pack.md': doc('Working in a TypeScript repo', inline='yes')})

        result = self.add()

        self.assertEqual(result.returncode, 1)
        self.assertIn('context/typescript/pack.md', result.stderr)
        self.assertIn('inline', result.stderr)


class OverlapTests(SyncCase):
    """A pack and a folder inside it installed from the same origin."""

    def setUp(self):
        super().setUp()
        self.publish({
            'pack.md': 'Prefer small PRs.\n',
            'typescript/pack.md': doc('Editing `**/*.ts`', 'Prefer unions.\n'),
        })
        self.agents_md = self.repo / 'AGENTS.md'

    def add_typescript(self, origin=None):
        return self.sync('add', 'typescript', str(origin or self.origin), '--path', 'context/typescript')

    def test_adding_a_folder_inside_an_installed_pack_stops_untouched(self):
        self.add()
        before = self.agents_md.read_text()

        result = self.add_typescript()

        self.assertEqual(result.returncode, 1)
        self.assertIn('house-rules', result.stderr)
        self.assertIn('typescript', result.stderr)
        self.assertEqual(self.agents_md.read_text(), before)

    def test_adding_a_pack_around_an_installed_one_stops_untouched(self):
        self.add_typescript()
        before = self.agents_md.read_text()

        result = self.add()

        self.assertEqual(result.returncode, 1)
        self.assertIn('house-rules', result.stderr)
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
            'typescript/pack.md': doc('Editing `**/*.ts`', 'Prefer unions.\n', optional='true'),
            'typescript/types.md': doc('Declaring types'),
            'style/pack.md': '---\ninline: true\n---\nUse tabs.\n',
        })
        self.agents_md = self.repo / 'AGENTS.md'
        self.synced = self.repo / 'docs' / 'agents' / 'packs' / 'typescript'

    def add_folder(self, name):
        return self.sync('add', name, str(self.origin), '--path', f'context/{name}')

    def test_pack_with_a_when_line_gets_a_row_in_its_block(self):
        result = self.add_folder('typescript')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(' -->\n## typescript context\n\n| When | Read |\n|---|---|\n'
                      '| Editing `**/*.ts` | `docs/agents/packs/typescript/pack.md` |\n<!-- context-packs:end',
                      self.agents_md.read_text())

    def test_pack_with_a_when_line_gets_an_index_of_its_rules_and_table(self):
        result = self.add_folder('typescript')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.synced / 'pack.md').read_text(),
                         'Prefer unions.\n\n## typescript context\n\n| When | Read |\n|---|---|\n'
                         '| Declaring types | `docs/agents/packs/typescript/types.md` |\n')

    def test_inline_pack_gets_its_rules_in_its_block(self):
        result = self.add_folder('style')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(' -->\nUse tabs.\n<!-- context-packs:end', self.agents_md.read_text())

    def test_nested_pack_named_pack_beside_a_root_index_stops_the_sync(self):
        self.publish({'typescript/pack/pack.md': doc('Packaging')})

        result = self.add_folder('typescript')

        self.assertEqual(result.returncode, 1)
        self.assertIn('context/typescript/pack', result.stderr)
        self.assertFalse(self.agents_md.exists())


class LocalNestedPackTests(SyncCase):
    """A nested pack in a pack in the synced repo: its docs stay where they are, and only its index is generated."""

    def setUp(self):
        super().setUp()
        self.docs = self.repo / 'docs' / 'agents' / 'project'
        files = {
            'design.md': doc('Changing the design', 'Keep it small.\n'),
            'deploy/pack.md': doc('Deploying', 'Ship on green.\n'),
            'deploy/rollback.md': doc('Rolling back', 'Revert first.\n'),
        }
        for path, text in files.items():
            (self.docs / path).parent.mkdir(parents=True, exist_ok=True)
            (self.docs / path).write_text(text)
        self.index = self.repo / 'docs' / 'agents' / 'packs' / 'project' / 'deploy.md'

    def add_project(self):
        return self.sync('add', 'project', '.', '--path', 'docs/agents/project')

    def test_nested_packs_index_is_generated_beside_the_copied_packs(self):
        result = self.add_project()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('| Deploying | `docs/agents/packs/project/deploy.md` |\n'
                      '| Changing the design | `docs/agents/project/design.md` |\n',
                      (self.repo / 'AGENTS.md').read_text())
        self.assertEqual(self.index.read_text(),
                         'Ship on green.\n\n## project/deploy context\n\n| When | Read |\n|---|---|\n'
                         '| Rolling back | `docs/agents/project/deploy/rollback.md` |\n')
        self.assertEqual(sorted(p.name for p in self.index.parent.iterdir()), ['deploy.md'])

    def test_local_packs_generated_index_edited_in_the_repo_stops_the_sync(self):
        self.add_project()
        self.index.write_text('Edited here.\n')

        result = self.sync()

        self.assertEqual(result.returncode, 1)
        self.assertIn('docs/agents/packs/project', result.stderr)
        self.assertEqual(self.index.read_text(), 'Edited here.\n')

    def test_local_optional_nested_pack_is_left_out_unless_picked(self):
        (self.docs / 'deploy' / 'pack.md').write_text(doc('Deploying', 'Ship on green.\n', optional='true'))

        left_out = self.add_project()

        self.assertEqual(left_out.returncode, 0, left_out.stderr)
        self.assertNotIn('Deploying', (self.repo / 'AGENTS.md').read_text())
        self.assertFalse(self.index.exists())

        picked = self.sync('docs', 'project', 'deploy')

        self.assertEqual(picked.returncode, 0, picked.stderr)
        self.assertIn('<!-- context-packs:start project from=. path=docs/agents/project docs=deploy -->\n',
                      (self.repo / 'AGENTS.md').read_text())
        self.assertTrue(self.index.exists())

    def test_editing_a_local_nested_packs_rules_regenerates_its_index_on_resync(self):
        self.add_project()
        (self.docs / 'deploy' / 'pack.md').write_text(doc('Deploying', 'Ship on green, never on Friday.\n'))

        result = self.sync()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.index.read_text().startswith('Ship on green, never on Friday.\n'))


if __name__ == '__main__':
    unittest.main()
