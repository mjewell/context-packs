import shutil

from test_cli import SyncCase, doc


class DocsTests(SyncCase):
    """The docs command, which lists every file the repo's tables point an agent at, for the review's read check."""

    def setUp(self):
        super().setUp()
        self.publish({
            'pack.md': 'Prefer small PRs.\n',
            'testing.md': doc('Writing tests', 'Test behavior.\n'),
            'frontend/pack.md': doc('Editing `web/**`', 'Keep components small.\n'),
            'frontend/react.md': doc('Writing React components', 'Use function components.\n'),
            'backend/pack.md': doc('always', 'Validate input.\n'),
            'backend/errors.md': doc('Handling errors', 'Raise, never return codes.\n'),
        })
        self.write('context-packs/project/design.md', doc('Changing the design', 'Keep it small.\n'))
        result = self.add()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_prints_every_doc_and_nested_index_the_tables_point_at(self):
        result = self.sync('docs')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'context-packs/gen/house-rules/backend/errors.md\n'
                                        'context-packs/gen/house-rules/frontend.md\n'
                                        'context-packs/gen/house-rules/frontend/react.md\n'
                                        'context-packs/gen/house-rules/testing.md\n'
                                        'context-packs/project/design.md\n')

    def test_every_path_it_prints_is_in_agents_md_or_an_index(self):
        listed = self.sync('docs').stdout.splitlines()
        tables = self.agents_md.read_text() + (self.gen / 'house-rules' / 'frontend.md').read_text()

        self.assertEqual([path for path in listed if f'`{path}`' not in tables], [])
        self.assertTrue(all((self.repo / path).is_file() for path in listed))

    def test_reads_the_synced_tables_without_fetching_any_pack(self):
        expected = self.sync('docs').stdout
        shutil.rmtree(self.root / 'house-rules.git')
        shutil.rmtree(self.root / 'cache')

        result = self.sync('docs')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, expected)


class SubfolderDocsTests(SyncCase):
    """A folder inside a repo, whose tables' paths start from the repo root."""

    def test_lists_and_reads_paths_from_the_repo_root(self):
        self.write('packages/web/context-packs/frontend/pack.md', doc('Editing `web/**`', 'Keep components small.\n'))
        self.write('packages/web/context-packs/frontend/react.md', doc('Writing React components'))
        folder = str(self.repo / 'packages' / 'web')
        self.assertEqual(self.sync('--dir', folder).returncode, 0)

        result = self.sync('--dir', folder, 'docs')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'packages/web/context-packs/frontend/react.md\n'
                                        'packages/web/context-packs/gen/frontend.md\n')
