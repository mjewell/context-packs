import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / 'src' / 'cli.py'

HEADER = ('<!-- context-packs:start header -->\n'
          '## Context Packs\n\n'
          'Context packs bring shared rules and docs in from elsewhere. Each pack has a block in this file holding its '
          "rules and a table of its context docs. Before starting work that a row in a pack's table matches, read its "
          "doc. A pack's block and its folder under `docs/agents/packs/` are copied from the `from` and `path` in the "
          "block's start marker: change them there, never here.\n"
          '<!-- context-packs:end sha256:c647a98f1885 -->\n')
EMPTY_HEADER = '<!-- context-packs:start header -->\n<!-- context-packs:end sha256:e3b0c44298fc -->\n'
EMPTY_END = '<!-- context-packs:end sha256:e3b0c44298fc -->\n'
END = '<!-- context-packs:end sha256:d3e10247057e -->\n'


def git(cwd, *args):
    return subprocess.run(['git', '-c', 'user.name=Test', '-c', 'user.email=test@example.com', *args], cwd=cwd,
                          check=True, text=True, capture_output=True).stdout.strip()


class SyncCase(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='context-packs-test-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        # A pack's origin and a checkout of it, so tests control the pack's content.
        self.origin, self.source = self.remote('house-rules')
        self.repo = self.root / 'repo'
        (self.repo / '.git').mkdir(parents=True)
        self.env = {**os.environ, 'XDG_CACHE_HOME': str(self.root / 'cache')}

    def remote(self, name):
        """A bare origin and a checkout of it."""
        origin = self.root / f'{name}.git'
        git(self.root, 'init', '--quiet', '--bare', '--initial-branch=main', str(origin))
        git(self.root, 'clone', '--quiet', str(origin), str(self.root / name))
        return origin, self.root / name

    def publish(self, files, checkout=None, folder='context'):
        """Commit files into a pack's folder, None deleting one, and push them to its origin. Returns the commit."""
        checkout = checkout or self.source
        for path, text in files.items():
            file = checkout / folder / path
            if text is None:
                git(checkout, 'rm', '--quiet', '-r', str(file))
                continue
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(text)
        git(checkout, 'add', '--all', folder)
        git(checkout, 'commit', '--quiet', '-m', 'Change the pack')
        git(checkout, 'push', '--quiet', 'origin', 'HEAD:main')
        return git(checkout, 'rev-parse', 'HEAD')

    def share(self, instructions):
        return self.publish({'agents.md': instructions})

    def doc_set(self, name, files):
        return self.publish({f'{name}/{path}': text for path, text in files.items()})

    def tag(self, name, checkout=None):
        checkout = checkout or self.source
        git(checkout, 'tag', name)
        git(checkout, 'push', '--quiet', 'origin', name)

    def start(self, ref=None):
        ref = ref or git(self.source, 'rev-parse', 'HEAD')
        return f'<!-- context-packs:start house-rules from={self.origin} path=context ref={ref} -->\n'

    def rules(self, ref=None):
        """AGENTS.md as a sync writes it from the pack's rules 'Prefer small PRs.', with no doc sets."""
        return HEADER + '\n' + self.start(ref) + 'Prefer small PRs.\n' + END

    def sync(self, *args, repo=None):
        return subprocess.run([sys.executable, str(CLI), str(repo or self.repo), *args],
                              text=True, capture_output=True, timeout=30, env=self.env)

    def add(self, *args):
        return self.sync('add', 'house-rules', str(self.origin), '--path', 'context', *args)


class SyncTests(SyncCase):
    def test_fresh_repo_gets_agents_md_holding_only_the_header(self):
        result = self.sync()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.repo / 'AGENTS.md').read_text(), HEADER)

    def test_fresh_repo_gets_claude_md_linked_to_agents_md(self):
        result = self.sync()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(os.readlink(self.repo / 'CLAUDE.md'), 'AGENTS.md')

    def test_block_edited_in_the_repo_stops_the_sync_untouched(self):
        self.share('Prefer small PRs.\n')
        self.add()
        agents_md = self.repo / 'AGENTS.md'
        edited = agents_md.read_text().replace('small PRs', 'tiny PRs')
        agents_md.write_text(edited)
        self.share('Prefer small PRs.\nWrite tests first.\n')

        result = self.sync('update')

        self.assertEqual(result.returncode, 1)
        self.assertIn('AGENTS.md', result.stderr)
        self.assertEqual(agents_md.read_text(), edited)

    def test_header_block_edited_in_the_repo_stops_the_sync_untouched(self):
        self.sync()
        agents_md = self.repo / 'AGENTS.md'
        edited = agents_md.read_text().replace('never here', 'rarely here')
        agents_md.write_text(edited)

        result = self.sync()

        self.assertEqual(result.returncode, 1)
        self.assertIn('header block', result.stderr)
        self.assertEqual(agents_md.read_text(), edited)

    def test_agents_md_without_blocks_stops_and_shows_the_lines_to_add(self):
        agents_md = self.repo / 'AGENTS.md'
        agents_md.write_text('# Repo\n')

        result = self.sync()

        self.assertEqual(result.returncode, 1)
        self.assertIn(EMPTY_HEADER, result.stderr)
        self.assertEqual(agents_md.read_text(), '# Repo\n')

    def test_claude_md_that_is_not_the_link_stops_the_sync_untouched(self):
        (self.repo / 'CLAUDE.md').write_text('Old rules.\n')

        result = self.sync()

        self.assertEqual(result.returncode, 1)
        self.assertIn('CLAUDE.md', result.stderr)
        self.assertEqual(sorted(p.name for p in self.repo.iterdir()), ['.git', 'CLAUDE.md'])

    def test_missing_repo_folder_stops_the_sync(self):
        missing = self.repo / 'not-a-repo'

        result = self.sync(repo=missing)

        self.assertEqual(result.returncode, 1)
        self.assertIn(f'context-packs: {missing} is not a folder', result.stderr)

    def test_folder_that_is_not_a_repo_root_stops_the_sync_untouched(self):
        shutil.rmtree(self.repo / '.git')

        result = self.sync()

        self.assertEqual(result.returncode, 1)
        self.assertIn('not the root of a git repo', result.stderr)
        self.assertEqual(list(self.repo.iterdir()), [])

    def test_pack_block_repeated_stops_the_sync_untouched(self):
        self.share('Prefer small PRs.\n')
        self.add()
        agents_md = self.repo / 'AGENTS.md'
        pack = agents_md.read_text()[len(HEADER) + 1:]
        doubled = agents_md.read_text() + '\n' + pack
        agents_md.write_text(doubled)

        result = self.sync()

        self.assertEqual(result.returncode, 1)
        self.assertIn('more than one house-rules block', result.stderr)
        self.assertEqual(agents_md.read_text(), doubled)

    def test_blocks_not_starting_with_the_header_stop_the_sync_untouched(self):
        self.share('Prefer small PRs.\n')
        agents_md = self.repo / 'AGENTS.md'
        pack_only = self.start() + EMPTY_END
        agents_md.write_text(pack_only)

        result = self.sync()

        self.assertEqual(result.returncode, 1)
        self.assertIn('start with the header block', result.stderr)
        self.assertEqual(agents_md.read_text(), pack_only)

    def test_text_between_blocks_stops_the_sync_untouched(self):
        self.share('Prefer small PRs.\n')
        self.add()
        agents_md = self.repo / 'AGENTS.md'
        split = agents_md.read_text().replace(HEADER + '\n', HEADER + '\nUse pnpm.\n\n')
        agents_md.write_text(split)

        result = self.sync()

        self.assertEqual(result.returncode, 1)
        self.assertIn('between the context-packs blocks', result.stderr)
        self.assertEqual(agents_md.read_text(), split)

    def test_pack_folder_without_a_block_stops_the_sync_and_names_it(self):
        self.sync()
        stray = self.repo / 'docs' / 'agents' / 'packs' / 'acme' / 'index.md'
        stray.parent.mkdir(parents=True)
        stray.write_text('Use acme.\n')

        result = self.sync()

        self.assertEqual(result.returncode, 1)
        self.assertIn('docs/agents/packs/acme', result.stderr)
        self.assertTrue(stray.exists())

    def test_shared_rules_without_a_final_newline_still_resync(self):
        self.share('Prefer small PRs.')
        self.add()

        result = self.sync()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.repo / 'AGENTS.md').read_text(), self.rules())

    def test_agents_md_with_crlf_line_endings_stops_the_sync_untouched(self):
        agents_md = self.repo / 'AGENTS.md'
        crlf = ('# Repo\n\n' + EMPTY_HEADER).replace('\n', '\r\n')
        agents_md.write_bytes(crlf.encode())

        result = self.sync()

        self.assertEqual(result.returncode, 1)
        self.assertIn('CRLF', result.stderr)
        self.assertEqual(agents_md.read_bytes(), crlf.encode())

    def test_pasted_empty_header_block_gets_filled(self):
        agents_md = self.repo / 'AGENTS.md'
        agents_md.write_text('# Repo\n\n' + EMPTY_HEADER + '\nUse pnpm.\n')

        result = self.sync()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(agents_md.read_text(), '# Repo\n\n' + HEADER + '\nUse pnpm.\n')


class AddRemoveTests(SyncCase):
    def setUp(self):
        super().setUp()
        self.share('Prefer small PRs.\n')

    def test_add_installs_the_pack_pinned_to_its_origins_latest_commit(self):
        result = self.add()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.repo / 'AGENTS.md').read_text(), self.rules())

    def test_add_with_a_ref_pins_the_pack_there(self):
        first = git(self.source, 'rev-parse', 'HEAD')
        self.share('Prefer small PRs.\nWrite tests first.\n')

        result = self.add('--ref', first[:7])

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.repo / 'AGENTS.md').read_text(), self.rules(first))

    def test_add_with_a_branch_as_the_ref_stops_untouched(self):
        result = self.add('--ref', 'main')

        self.assertEqual(result.returncode, 1)
        self.assertIn('branch', result.stderr)
        self.assertFalse((self.repo / 'AGENTS.md').exists())

    def test_add_of_a_name_already_installed_stops_untouched(self):
        self.add()
        before = (self.repo / 'AGENTS.md').read_text()

        result = self.add()

        self.assertEqual(result.returncode, 1)
        self.assertIn('already has', result.stderr)
        self.assertEqual((self.repo / 'AGENTS.md').read_text(), before)

    def test_add_of_a_pack_in_the_repo_itself_syncs_its_working_tree(self):
        (self.repo / 'team-rules').mkdir()
        (self.repo / 'team-rules' / 'agents.md').write_text('Use pnpm.\n')

        result = self.sync('add', 'team', '.', '--path', 'team-rules')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.repo / 'AGENTS.md').read_text(),
                         HEADER + '\n<!-- context-packs:start team from=. path=team-rules -->\nUse pnpm.\n'
                         '<!-- context-packs:end sha256:8deb5dab0c1e -->\n')

    def test_remove_drops_the_packs_block_and_docs(self):
        self.doc_set('testing', {'index.md': '---\nwhen: Writing tests\ntier: required\n---\nTest behavior.\n'})
        self.add()

        result = self.sync('remove', 'house-rules')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.repo / 'AGENTS.md').read_text(), HEADER)
        self.assertFalse((self.repo / 'docs' / 'agents' / 'packs').exists())

    def test_remove_of_a_pack_not_installed_stops(self):
        self.sync()

        result = self.sync('remove', 'acme')

        self.assertEqual(result.returncode, 1)
        self.assertIn('acme', result.stderr)


class PinningTests(SyncCase):
    def setUp(self):
        super().setUp()
        self.pinned = self.share('Prefer small PRs.\n')
        self.add()
        self.agents_md = self.repo / 'AGENTS.md'

    def test_plain_resync_keeps_the_pinned_rules_after_the_pack_moves_on(self):
        self.share('Prefer small PRs.\nWrite tests first.\n')

        result = self.sync()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.agents_md.read_text(), self.rules(self.pinned))

    def test_update_takes_the_packs_latest_rules_and_keeps_the_repos_own_text(self):
        self.agents_md.write_text('# Repo\n\n' + self.agents_md.read_text() + '\nUse pnpm.\n')
        latest = self.share('Prefer small PRs.\nWrite tests first.\n')

        result = self.sync('update')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.agents_md.read_text(),
                         '# Repo\n\n' + HEADER + '\n' + self.start(latest) + 'Prefer small PRs.\nWrite tests first.\n'
                         '<!-- context-packs:end sha256:e9cecd87d052 -->\n\nUse pnpm.\n')

    def test_ref_missing_from_the_origin_stops_the_sync_untouched(self):
        missing = self.agents_md.read_text().replace(self.pinned, '0' * 40)
        self.agents_md.write_text(missing)

        result = self.sync()

        self.assertEqual(result.returncode, 1)
        self.assertIn('0' * 40, result.stderr)
        self.assertEqual(self.agents_md.read_text(), missing)

    def test_pack_block_without_a_ref_stops_the_sync_untouched(self):
        unpinned = self.agents_md.read_text().replace(f' ref={self.pinned}', '')
        self.agents_md.write_text(unpinned)

        result = self.sync()

        self.assertEqual(result.returncode, 1)
        self.assertIn('house-rules', result.stderr)
        self.assertIn('ref=', result.stderr)
        self.assertEqual(self.agents_md.read_text(), unpinned)

    def test_update_with_a_ref_pins_the_pack_there(self):
        self.share('Prefer small PRs.\nWrite tests first.\n')
        self.tag('v1.0.0')

        result = self.sync('update', 'house-rules', '--ref', 'v1.0.0')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(self.start('v1.0.0') + 'Prefer small PRs.\nWrite tests first.\n', self.agents_md.read_text())

    def test_update_with_a_ref_needs_exactly_one_pack(self):
        before = self.agents_md.read_text()

        result = self.sync('update', '--ref', self.pinned)

        self.assertEqual(result.returncode, 1)
        self.assertIn('one pack', result.stderr)
        self.assertEqual(self.agents_md.read_text(), before)

    def test_update_of_a_pack_not_installed_stops(self):
        result = self.sync('update', 'acme')

        self.assertEqual(result.returncode, 1)
        self.assertIn('acme', result.stderr)


class VersionTests(SyncCase):
    """A pack pinned to a tag follows the newest release in its tag's series."""

    def setUp(self):
        super().setUp()
        self.share('Prefer small PRs.\n')
        self.tag('v1.2.0')
        self.add('--ref', 'v1.2.0')
        self.agents_md = self.repo / 'AGENTS.md'

    def test_add_with_a_tag_pins_the_pack_to_the_tag(self):
        self.assertEqual(self.agents_md.read_text(), self.rules('v1.2.0'))

    def test_update_moves_to_the_newest_release_in_the_series(self):
        self.share('Prefer small PRs.\nWrite tests first.\n')
        self.tag('v1.9.0')
        self.tag('v1.10.0')
        self.share('Prefer tiny PRs.\n')
        self.tag('v2.0.0-rc1')
        self.tag('acme-v9.0.0')

        result = self.sync('update')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(self.start('v1.10.0') + 'Prefer small PRs.\nWrite tests first.\n', self.agents_md.read_text())

    def test_update_keeps_the_tag_when_no_release_is_newer(self):
        self.share('Prefer tiny PRs.\n')

        result = self.sync('update')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.agents_md.read_text(), self.rules('v1.2.0'))


class SeveralPacksTests(SyncCase):
    def setUp(self):
        super().setUp()
        self.share('Prefer small PRs.\n')
        self.add()
        self.acme_origin, self.acme = self.remote('acme')
        self.acme_ref = self.publish({
            'agents.md': 'Use acme.\n',
            'deploy/index.md': '---\nwhen: Deploying\ntier: required\n---\nShip it.\n',
            'billing/index.md': '---\nwhen: Editing billing\n---\nCharge once.\n',
        }, checkout=self.acme, folder='plugins/x')
        self.agents_md = self.repo / 'AGENTS.md'

    def add_acme(self, *args):
        return self.sync('add', 'acme', str(self.acme_origin), '--path', 'plugins/x', *args)

    def acme_start(self, ref):
        return f'<!-- context-packs:start acme from={self.acme_origin} path=plugins/x ref={ref} -->\n'

    def test_added_pack_gets_its_own_block_after_the_others(self):
        result = self.add_acme()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.agents_md.read_text(),
                         self.rules() + '\n' + self.acme_start(self.acme_ref) + 'Use acme.\n\n## acme context\n\n'
                         '| When | Read |\n|---|---|\n| Deploying | `docs/agents/packs/acme/deploy/index.md` |\n'
                         '<!-- context-packs:end sha256:10e161169c08 -->\n')
        self.assertEqual((self.repo / 'docs' / 'agents' / 'packs' / 'acme' / 'deploy' / 'index.md').read_text(),
                         '---\nwhen: Deploying\ntier: required\n---\nShip it.\n')

    def test_update_moves_every_pinned_pack(self):
        self.add_acme()
        latest = self.share('Prefer small PRs.\nWrite tests first.\n')
        acme_latest = self.publish({'agents.md': 'Use acme v2.\n'}, checkout=self.acme, folder='plugins/x')

        result = self.sync('update')

        self.assertEqual(result.returncode, 0, result.stderr)
        text = self.agents_md.read_text()
        self.assertIn(self.start(latest), text)
        self.assertIn(self.acme_start(acme_latest) + 'Use acme v2.\n', text)

    def test_update_by_name_moves_only_that_pack(self):
        self.add_acme()
        self.share('Prefer small PRs.\nWrite tests first.\n')
        acme_latest = self.publish({'agents.md': 'Use acme v2.\n'}, checkout=self.acme, folder='plugins/x')

        result = self.sync('update', 'acme')

        self.assertEqual(result.returncode, 0, result.stderr)
        text = self.agents_md.read_text()
        self.assertIn(self.rules(git(self.source, 'rev-parse', 'HEAD~1')), text)
        self.assertIn(self.acme_start(acme_latest), text)

    def test_choosing_doc_sets_changes_only_the_named_pack(self):
        self.add_acme()

        result = self.sync('docs', 'acme', 'billing')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(sorted(p.name for p in (self.repo / 'docs' / 'agents' / 'packs' / 'acme').iterdir()),
                         ['billing', 'deploy'])
        self.assertTrue(self.agents_md.read_text().startswith(self.rules()))

    def test_list_shows_every_pack_and_its_doc_sets(self):
        self.add_acme('--docs', 'billing')

        result = self.sync('list')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout,
                         f'house-rules  {self.origin}  context @ {git(self.source, "rev-parse", "HEAD")}\n'
                         f'acme  {self.acme_origin}  plugins/x @ {self.acme_ref}\n'
                         '  [x] billing: Editing billing\n'
                         '  [x] deploy (required): Deploying\n')


class DocSetTests(SyncCase):
    def setUp(self):
        super().setUp()
        self.share('Prefer small PRs.\n')
        self.doc_set('typescript', {
            'index.md': '---\nwhen: Editing `**/*.ts`\n---\nSee react.md for components.\n',
            'react.md': 'Use function components.\n',
        })
        self.doc_set('skills', {'index.md': '---\nwhen: Editing `**/SKILL.md`\n---\nKeep skills short.\n'})
        self.synced = self.repo / 'docs' / 'agents' / 'packs' / 'house-rules'

    def test_chosen_doc_sets_are_copied_in_and_listed_in_the_block(self):
        result = self.add('--docs', 'typescript,skills')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.synced / 'typescript' / 'react.md').read_text(), 'Use function components.\n')
        self.assertEqual((self.synced / 'skills' / 'index.md').read_text(),
                         '---\nwhen: Editing `**/SKILL.md`\n---\nKeep skills short.\n')
        self.assertIn('Prefer small PRs.\n\n## house-rules context\n\n| When | Read |\n|---|---|\n'
                      '| Editing `**/SKILL.md` | `docs/agents/packs/house-rules/skills/index.md` |\n'
                      '| Editing `**/*.ts` | `docs/agents/packs/house-rules/typescript/index.md` |\n'
                      '<!-- context-packs:end',
                      (self.repo / 'AGENTS.md').read_text())

    def test_update_keeps_the_installed_doc_sets_and_updates_them(self):
        self.add('--docs', 'skills')
        self.doc_set('skills', {'index.md': '---\nwhen: Editing `**/SKILL.md`\n---\nKeep skills shorter.\n'})

        result = self.sync('update')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(sorted(p.name for p in self.synced.iterdir()), ['skills'])
        self.assertIn('Keep skills shorter.', (self.synced / 'skills' / 'index.md').read_text())

    def test_doc_sets_left_out_of_the_choice_are_removed(self):
        self.add('--docs', 'typescript,skills')

        result = self.sync('docs', 'house-rules', 'skills')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(sorted(p.name for p in self.synced.iterdir()), ['skills'])
        self.assertNotIn('typescript', (self.repo / 'AGENTS.md').read_text())

    def test_choosing_no_doc_sets_removes_the_table_and_the_folder(self):
        self.add('--docs', 'skills')

        result = self.sync('docs', 'house-rules', '')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.repo / 'docs' / 'agents' / 'packs').exists())
        self.assertEqual((self.repo / 'AGENTS.md').read_text(), self.rules())

    def test_synced_doc_edited_in_the_repo_stops_the_sync_untouched(self):
        self.add('--docs', 'skills')
        doc = self.synced / 'skills' / 'index.md'
        doc.write_text('Edited here.\n')
        before = (self.repo / 'AGENTS.md').read_text()

        result = self.sync()

        self.assertEqual(result.returncode, 1)
        self.assertIn('docs/agents/packs/house-rules', result.stderr)
        self.assertEqual(doc.read_text(), 'Edited here.\n')
        self.assertEqual((self.repo / 'AGENTS.md').read_text(), before)

    def test_unknown_doc_set_stops_the_sync_and_names_the_available_ones(self):
        result = self.add('--docs', 'python')

        self.assertEqual(result.returncode, 1)
        self.assertIn('python', result.stderr)
        self.assertIn('skills, typescript', result.stderr)
        self.assertFalse((self.repo / 'AGENTS.md').exists())

    def test_installed_doc_set_gone_from_the_pack_stops_the_update(self):
        self.add('--docs', 'skills')
        self.publish({'skills': None})

        result = self.sync('update')

        self.assertEqual(result.returncode, 1)
        self.assertIn('skills', result.stderr)
        self.assertTrue((self.synced / 'skills' / 'index.md').exists())

    def test_doc_set_without_a_when_line_stops_the_sync(self):
        self.doc_set('python', {'index.md': 'Use uv.\n'})

        result = self.add('--docs', 'python')

        self.assertEqual(result.returncode, 1)
        self.assertIn('context/python/index.md', result.stderr)

    def test_stray_file_in_the_synced_folder_stops_the_sync_and_names_it(self):
        self.add('--docs', 'skills')
        (self.synced / '.DS_Store').write_text('')

        result = self.sync()

        self.assertEqual(result.returncode, 1)
        self.assertIn('docs/agents/packs/house-rules/.DS_Store is not a doc set', result.stderr)
        self.assertTrue((self.synced / '.DS_Store').exists())

    def test_list_shows_every_doc_set_and_marks_the_installed_ones(self):
        self.add('--docs', 'skills')
        before = (self.repo / 'AGENTS.md').read_text()

        result = self.sync('list')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout,
                         f'house-rules  {self.origin}  context @ {git(self.source, "rev-parse", "HEAD")}\n'
                         '  [x] skills: Editing `**/SKILL.md`\n'
                         '  [ ] typescript: Editing `**/*.ts`\n')
        self.assertEqual((self.repo / 'AGENTS.md').read_text(), before)


class RequiredDocSetTests(SyncCase):
    def setUp(self):
        super().setUp()
        self.share('Prefer small PRs.\n')
        self.doc_set('testing', {'index.md': '---\nwhen: Writing tests\ntier: required\n---\nTest behavior.\n'})
        self.doc_set('typescript', {'index.md': '---\nwhen: Editing `**/*.ts`\n---\nUse unions.\n'})
        self.synced = self.repo / 'docs' / 'agents' / 'packs' / 'house-rules'

    def test_required_sets_are_installed_and_listed_without_being_chosen(self):
        result = self.add()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.synced / 'testing' / 'index.md').read_text(),
                         '---\nwhen: Writing tests\ntier: required\n---\nTest behavior.\n')
        self.assertIn('| Writing tests | `docs/agents/packs/house-rules/testing/index.md` |\n',
                      (self.repo / 'AGENTS.md').read_text())

    def test_required_sets_stay_when_no_doc_sets_are_chosen(self):
        self.add('--docs', 'typescript')

        result = self.sync('docs', 'house-rules', '')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(sorted(p.name for p in self.synced.iterdir()), ['testing'])

    def test_list_marks_the_required_sets(self):
        self.add()

        result = self.sync('list')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.endswith('  [x] testing (required): Writing tests\n'
                                               '  [ ] typescript: Editing `**/*.ts`\n'), result.stdout)

    def test_unknown_tier_stops_the_sync(self):
        self.doc_set('python', {'index.md': '---\nwhen: Editing `**/*.py`\ntier: recommended\n---\n'})

        result = self.add()

        self.assertEqual(result.returncode, 1)
        self.assertIn('context/python/index.md', result.stderr)
        self.assertFalse((self.repo / 'AGENTS.md').exists())


class WorkspaceTests(SyncCase):
    def setUp(self):
        super().setUp()
        self.share('Prefer small PRs.\n')
        shutil.rmtree(self.repo / '.git')

    def test_workspace_gets_the_packs_but_no_claude_md(self):
        result = self.sync('--workspace', 'add', 'house-rules', str(self.origin), '--path', 'context')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.repo / 'AGENTS.md').read_text(), self.rules())
        self.assertFalse(os.path.lexists(self.repo / 'CLAUDE.md'))

    def test_workspace_with_a_claude_md_stops_the_sync_untouched(self):
        (self.repo / 'CLAUDE.md').symlink_to('AGENTS.md')

        result = self.sync('--workspace')

        self.assertEqual(result.returncode, 1)
        self.assertIn('CLAUDE.md', result.stderr)
        self.assertFalse((self.repo / 'AGENTS.md').exists())

    def test_workspace_whose_agents_md_is_a_link_stops_the_sync_untouched(self):
        target = self.source / 'old-rules.md'
        (self.repo / 'AGENTS.md').symlink_to(target)

        result = self.sync('--workspace')

        self.assertEqual(result.returncode, 1)
        self.assertIn('symlink', result.stderr)
        self.assertFalse(target.exists())

    def test_workspace_flag_on_a_repo_stops_the_sync(self):
        (self.repo / '.git').mkdir()

        result = self.sync('--workspace')

        self.assertEqual(result.returncode, 1)
        self.assertIn('is a git repo', result.stderr)
        self.assertFalse((self.repo / 'AGENTS.md').exists())


if __name__ == '__main__':
    unittest.main()
