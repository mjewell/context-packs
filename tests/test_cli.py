import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / 'src' / 'cli.py'

START = '<!-- context-packs:start -->\n'
# The end marker with its hash masked, as SyncCase.agents() reads it.
END = '<!-- context-packs:end sha256:x -->\n'
EMPTY = START + '<!-- context-packs:end sha256:e3b0c44298fc -->\n'
HEADER = ('## Context Packs\n\n'
          'Context packs bring shared rules and docs in from elsewhere. Each pack has its rules and a table of its '
          'context docs here, and a doc may hold a table of its own. Before starting work that a row in any of these '
          'tables matches, read its doc. The packs here, and everything under `context-packs/gen/`, are generated '
          'from `context-packs/`: change them there, never here.\n')


def block(body=''):
    """The context-packs block holding the header and body, with its hash masked."""
    return START + HEADER + ('\n' + body if body else '') + END


def masked(text):
    return re.sub(r'sha256:[0-9a-f]{12}', 'sha256:x', text)


def doc(when, text='', **fields):
    front = ''.join(f'{key}: {value}\n' for key, value in fields.items())
    return f'---\nwhen: {when}\n{front}---\n{text}'


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
        self.packs = self.repo / 'context-packs'
        self.gen = self.packs / 'gen'
        self.agents_md = self.repo / 'AGENTS.md'
        self.env = {**os.environ, 'XDG_CACHE_HOME': str(self.root / 'cache')}

    def remote(self, name):
        """A bare origin, by its git URL, and a checkout of it."""
        origin = self.root / f'{name}.git'
        git(self.root, 'init', '--quiet', '--bare', '--initial-branch=main', str(origin))
        git(self.root, 'clone', '--quiet', str(origin), str(self.root / name))
        return origin.as_uri(), self.root / name

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
        return self.publish({'pack.md': instructions})

    def tag(self, name, checkout=None):
        checkout = checkout or self.source
        git(checkout, 'tag', name)
        git(checkout, 'push', '--quiet', 'origin', name)

    def write(self, path, text):
        """Write a file in the repo."""
        file = self.repo / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text)
        return file

    def agents(self):
        """AGENTS.md with its block's hash masked."""
        return masked(self.agents_md.read_text())

    def rules(self):
        """AGENTS.md as a sync writes it from the pack's rules 'Prefer small PRs.', with no docs."""
        return block('Prefer small PRs.\n')

    def import_md(self, id='house-rules'):
        return self.packs / id / 'pack.md'

    def front(self, ref, when=None, origin=None, path='context'):
        """An import pack's front matter, as add writes it."""
        return ('---\n' + f'when: {when}\n' * bool(when) + f'from: {origin or self.origin}\n'
                + f'path: {path}\n' * bool(path) + f'ref: {ref}\n---\n')

    def pin(self, id='house-rules'):
        """The ref the pack's import pack pins it to."""
        text = self.import_md(id).read_text()
        return next(line[len('ref: '):] for line in text.split('\n') if line.startswith('ref: '))

    def sync(self, *args, cwd=None):
        return subprocess.run([sys.executable, str(CLI), *args], cwd=cwd or self.repo,
                              text=True, capture_output=True, timeout=30, env=self.env)

    def add(self, *args, id='house-rules'):
        return self.sync('add', id, str(self.origin), '--path', 'context', *args)


class SyncTests(SyncCase):
    def test_fresh_repo_gets_agents_md_holding_only_the_header(self):
        result = self.sync()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.agents(), block())

    def test_fresh_repo_gets_claude_md_linked_to_agents_md(self):
        result = self.sync()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(os.readlink(self.repo / 'CLAUDE.md'), 'AGENTS.md')

    def test_block_edited_in_the_repo_stops_the_sync_untouched(self):
        self.share('Prefer small PRs.\n')
        self.add()
        edited = self.agents_md.read_text().replace('small PRs', 'tiny PRs')
        self.agents_md.write_text(edited)
        self.share('Prefer small PRs.\nWrite tests first.\n')

        result = self.sync('update')

        self.assertEqual(result.returncode, 1)
        self.assertIn('was edited', result.stderr)
        self.assertEqual(self.agents_md.read_text(), edited)

    def test_header_edited_in_the_repo_stops_the_sync_untouched(self):
        self.sync()
        edited = self.agents_md.read_text().replace('never here', 'rarely here')
        self.agents_md.write_text(edited)

        result = self.sync()

        self.assertEqual(result.returncode, 1)
        self.assertIn('was edited', result.stderr)
        self.assertEqual(self.agents_md.read_text(), edited)

    def test_agents_md_without_a_block_stops_and_shows_the_lines_to_add(self):
        self.agents_md.write_text('# Repo\n')

        result = self.sync()

        self.assertEqual(result.returncode, 1)
        self.assertIn(EMPTY, result.stderr)
        self.assertEqual(self.agents_md.read_text(), '# Repo\n')

    def test_dir_syncs_that_folder_instead_of_the_current_one(self):
        elsewhere = self.root / 'elsewhere'
        elsewhere.mkdir()

        result = self.sync('--dir', str(self.repo), cwd=elsewhere)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.agents(), block())
        self.assertEqual(list(elsewhere.iterdir()), [])

    def test_missing_dir_stops_the_sync(self):
        missing = self.repo / 'not-a-repo'

        result = self.sync('--dir', str(missing))

        self.assertEqual(result.returncode, 1)
        self.assertIn(f'context-packs: {missing} is not a folder', result.stderr)

    def test_usage_errors_name_the_tool(self):
        result = self.sync('publish')

        self.assertEqual(result.returncode, 2)
        self.assertTrue(result.stderr.startswith('usage: context-packs '), result.stderr)

    def test_agents_md_that_is_a_link_stops_the_sync_untouched(self):
        target = self.source / 'old-rules.md'
        self.agents_md.symlink_to(target)

        result = self.sync()

        self.assertEqual(result.returncode, 1)
        self.assertIn('symlink', result.stderr)
        self.assertFalse(target.exists())

    def test_folder_that_is_not_a_repo_gets_agents_md_and_claude_md(self):
        shutil.rmtree(self.repo / '.git')

        result = self.sync()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.agents(), block())
        self.assertEqual(os.readlink(self.repo / 'CLAUDE.md'), 'AGENTS.md')

    def test_block_repeated_stops_the_sync_untouched(self):
        self.sync()
        doubled = self.agents_md.read_text() + '\n' + EMPTY
        self.agents_md.write_text(doubled)

        result = self.sync()

        self.assertEqual(result.returncode, 1)
        self.assertIn('more than one context-packs block', result.stderr)
        self.assertEqual(self.agents_md.read_text(), doubled)

    def test_blocks_from_an_older_version_stop_and_show_the_lines_to_use(self):
        old = ('# Repo\n\n<!-- context-packs:start header -->\n<!-- context-packs:end sha256:e3b0c44298fc -->\n\n'
               '<!-- context-packs:start core path=docs/agents/core -->\n<!-- context-packs:end sha256:e3b0c44298fc -->\n')
        self.agents_md.write_text(old)

        result = self.sync()

        self.assertEqual(result.returncode, 1)
        self.assertIn('older version', result.stderr)
        self.assertIn(EMPTY, result.stderr)
        self.assertEqual(self.agents_md.read_text(), old)

    def test_shared_rules_without_a_final_newline_still_resync(self):
        self.share('Prefer small PRs.')
        self.add()

        result = self.sync()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.agents(), self.rules())

    def test_agents_md_with_crlf_line_endings_stops_the_sync_untouched(self):
        crlf = ('# Repo\n\n' + EMPTY).replace('\n', '\r\n')
        self.agents_md.write_bytes(crlf.encode())

        result = self.sync()

        self.assertEqual(result.returncode, 1)
        self.assertIn('CRLF', result.stderr)
        self.assertEqual(self.agents_md.read_bytes(), crlf.encode())

    def test_pasted_empty_block_gets_filled(self):
        self.agents_md.write_text('# Repo\n\n' + EMPTY + '\nUse pnpm.\n')

        result = self.sync()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.agents(), '# Repo\n\n' + block() + '\nUse pnpm.\n')

    def test_stray_file_in_the_generated_folder_stops_the_sync(self):
        self.sync()
        stray = self.write('context-packs/gen/acme/index.md', 'Use acme.\n')

        result = self.sync()

        self.assertEqual(result.returncode, 1)
        self.assertIn('context-packs/gen', result.stderr)
        self.assertTrue(stray.exists())


class AddRemoveTests(SyncCase):
    def setUp(self):
        super().setUp()
        self.first = self.share('Prefer small PRs.\n')

    def test_add_writes_an_import_pack_pinned_to_its_origins_latest_commit(self):
        result = self.add()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.import_md().read_text(), self.front(self.first))
        self.assertEqual(self.agents(), self.rules())

    def test_add_with_a_ref_pins_the_pack_there(self):
        self.share('Prefer small PRs.\nWrite tests first.\n')

        result = self.add('--ref', self.first[:7])

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.agents(), self.rules())
        self.assertEqual(self.pin(), self.first)

    def test_add_with_a_branch_as_the_ref_stops_untouched(self):
        result = self.add('--ref', 'main')

        self.assertEqual(result.returncode, 1)
        self.assertIn('branch', result.stderr)
        self.assertFalse(self.agents_md.exists())
        self.assertFalse(self.packs.exists())

    def test_add_where_a_folder_already_is_stops_untouched(self):
        self.add()
        before = self.agents_md.read_text()

        result = self.add()

        self.assertEqual(result.returncode, 1)
        self.assertIn('context-packs/house-rules already exists', result.stderr)
        self.assertEqual(self.agents_md.read_text(), before)

    def test_add_at_a_nested_id_writes_the_import_pack_there(self):
        result = self.add(id='shared/house-rules')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.import_md('shared/house-rules').read_text(), self.front(self.first))
        self.assertEqual(self.agents(), self.rules())

    def test_add_of_an_id_that_isnt_a_folder_under_context_packs_stops(self):
        for id in ('gen', '../rules', '.rules', 'a//b', '/rules'):
            with self.subTest(id=id):
                result = self.add(id=id)

                self.assertEqual(result.returncode, 1)
                self.assertIn(f"{id} can't name a pack", result.stderr)
                self.assertFalse(self.agents_md.exists())

    def test_add_of_a_folder_in_the_repo_imports_it_where_it_is(self):
        self.write('team-rules/pack.md', 'Use pnpm.\n')

        result = self.sync('add', 'team', 'team-rules')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.import_md('team').read_text(), '---\nfrom: team-rules\n---\n')
        self.assertEqual(self.agents(), block('Use pnpm.\n'))

    def test_remove_drops_the_import_pack_and_its_generated_files(self):
        self.publish({'testing.md': doc('Writing tests', 'Test behavior.\n')})
        self.add()

        result = self.sync('remove', 'house-rules')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.agents(), block())
        self.assertFalse(self.import_md().parent.exists())
        self.assertFalse(self.gen.exists())

    def test_remove_of_a_pack_not_installed_stops(self):
        self.sync()

        result = self.sync('remove', 'acme')

        self.assertEqual(result.returncode, 1)
        self.assertIn('acme', result.stderr)

    def test_remove_of_the_repos_own_folder_stops_and_keeps_it(self):
        design = self.write('context-packs/project/design.md', doc('Changing the design'))
        self.sync()

        result = self.sync('remove', 'project')

        self.assertEqual(result.returncode, 1)
        self.assertIn('project', result.stderr)
        self.assertTrue(design.exists())


class RootTests(SyncCase):
    """The repo's own docs and rules, written in context-packs/ itself, and listed where they are."""

    def setUp(self):
        super().setUp()
        self.write('context-packs/project/deploy/index.md', doc('Deploying', 'Ship it.\n'))
        self.write('context-packs/project/design.md', doc('Changing the design', 'Keep it small.\n'))

    def test_docs_in_context_packs_are_listed_where_they_are(self):
        result = self.sync()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.agents(),
                         block('## Context\n\n| When | Read |\n|---|---|\n'
                               '| Deploying | `context-packs/project/deploy/index.md` |\n'
                               '| Changing the design | `context-packs/project/design.md` |\n'))
        self.assertFalse(self.gen.exists())

    def test_pack_md_in_context_packs_is_inlined_before_its_table(self):
        self.write('context-packs/pack.md', 'Use pnpm.\n')

        result = self.sync()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(HEADER + '\nUse pnpm.\n\n## Context\n', self.agents())

    def test_when_on_the_pack_md_in_context_packs_stops_the_sync(self):
        self.write('context-packs/pack.md', doc('Working on anything', 'Use pnpm.\n'))

        result = self.sync()

        self.assertEqual(result.returncode, 1)
        self.assertIn('context-packs/pack.md', result.stderr)
        self.assertIn('when', result.stderr)

    def test_editing_a_doc_needs_no_resync(self):
        self.sync()
        before = self.agents_md.read_text()
        self.write('context-packs/project/design.md', doc('Changing the design', 'Keep it smaller.\n'))

        result = self.sync()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.agents_md.read_text(), before)

    def test_new_doc_joins_the_table_on_resync(self):
        self.sync()
        self.write('context-packs/project/billing.md', doc('Editing billing', 'Charge once.\n'))

        result = self.sync()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('| Editing billing | `context-packs/project/billing.md` |\n', self.agents())


class SiblingPackTests(SyncCase):
    """A pack in a folder beside the synced repo, imported by its path, which syncs from its working tree."""

    def setUp(self):
        super().setUp()
        self.publish({'pack.md': 'Prefer small PRs.\n', 'testing.md': doc('Writing tests', 'Test behavior.\n')})

    def add_sibling(self, *args):
        return self.sync('add', 'house-rules', '../house-rules', '--path', 'context', *args)

    def test_sibling_pack_syncs_its_working_tree_and_lists_its_docs_where_they_are(self):
        (self.source / 'context' / 'pack.md').write_text('Prefer tiny PRs.\n')

        result = self.add_sibling()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.import_md().read_text(), '---\nfrom: ../house-rules\npath: context\n---\n')
        self.assertEqual(self.agents(),
                         block('Prefer tiny PRs.\n\n## house-rules context\n\n| When | Read |\n|---|---|\n'
                               '| Writing tests | `../house-rules/context/testing.md` |\n'))
        self.assertFalse(self.gen.exists())

    def test_editing_a_sibling_doc_needs_no_resync(self):
        self.add_sibling()
        before = self.agents_md.read_text()
        (self.source / 'context' / 'testing.md').write_text(doc('Writing tests', 'Test behavior only.\n'))

        result = self.sync()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.agents_md.read_text(), before)

    def test_missing_sibling_folder_stops_the_sync(self):
        self.add_sibling()
        before = self.agents_md.read_text()
        shutil.rmtree(self.source)

        result = self.sync()

        self.assertEqual(result.returncode, 1)
        self.assertIn('../house-rules/context', result.stderr)
        self.assertEqual(self.agents_md.read_text(), before)

    def test_sibling_pack_takes_no_ref(self):
        result = self.add_sibling('--ref', 'v1.0.0')

        self.assertEqual(result.returncode, 1)
        self.assertIn('--ref', result.stderr)
        self.assertFalse(self.agents_md.exists())

    def test_sibling_pack_with_a_ref_in_its_import_pack_stops(self):
        self.add_sibling()
        self.import_md().write_text('---\nfrom: ../house-rules\npath: context\nref: v1.0.0\n---\n')

        result = self.sync()

        self.assertEqual(result.returncode, 1)
        self.assertIn('context-packs/house-rules/pack.md', result.stderr)
        self.assertIn('ref', result.stderr)

    def test_when_on_a_sibling_pack_gives_it_a_row(self):
        result = self.add_sibling('--when', 'Reviewing a PR')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('| Reviewing a PR | `context-packs/gen/house-rules/pack.md` |\n', self.agents())

    def test_absolute_path_is_a_folder_on_disk_too(self):
        (self.source / 'context' / 'pack.md').write_text('Prefer tiny PRs.\n')

        result = self.sync('add', 'house-rules', str(self.source), '--path', 'context')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(HEADER + '\nPrefer tiny PRs.\n', self.agents())
        self.assertIn(f'| Writing tests | `{self.source}/context/testing.md` |', self.agents())
        self.assertFalse(self.gen.exists())

    def test_scp_style_origin_is_a_git_url(self):
        result = subprocess.run([sys.executable, str(CLI), 'add', 'acme', 'git@example.invalid:acme/rules.git'],
                                cwd=self.repo, text=True, capture_output=True, timeout=30,
                                env={**self.env, 'GIT_SSH_COMMAND': 'false'})

        self.assertEqual(result.returncode, 1)
        self.assertIn('git ls-remote', result.stderr)

    def test_update_leaves_a_sibling_pack_alone(self):
        self.add_sibling()
        before = self.agents_md.read_text()

        result = self.sync('update')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.agents_md.read_text(), before)

    def test_update_with_a_ref_of_a_sibling_pack_stops(self):
        self.add_sibling()

        result = self.sync('update', 'house-rules', '--ref', 'v1.0.0')

        self.assertEqual(result.returncode, 1)
        self.assertIn('--ref', result.stderr)


class PackShapeTests(SyncCase):
    def test_doc_is_copied_and_listed(self):
        self.publish({'billing.md': doc('Billing', 'Charge once.\n')})

        result = self.add()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.gen / 'house-rules' / 'billing.md').read_text(), doc('Billing', 'Charge once.\n'))
        self.assertEqual(self.agents(),
                         block('## house-rules context\n\n| When | Read |\n|---|---|\n'
                               '| Billing | `context-packs/gen/house-rules/billing.md` |\n'))
        self.assertEqual(self.sync().returncode, 0)

    def test_front_matter_key_the_tool_doesnt_know_stops_the_sync(self):
        self.publish({'billing.md': doc('Billing', 'Charge once.\n', owner='payments')})

        result = self.add()

        self.assertEqual(result.returncode, 1)
        self.assertIn('context/billing.md', result.stderr)
        self.assertIn('owner', result.stderr)
        self.assertFalse(self.agents_md.exists())
        self.assertFalse(self.packs.exists())


class PinningTests(SyncCase):
    def setUp(self):
        super().setUp()
        self.pinned = self.share('Prefer small PRs.\n')
        self.add()

    def test_plain_resync_keeps_the_pinned_rules_after_the_pack_moves_on(self):
        self.share('Prefer small PRs.\nWrite tests first.\n')

        result = self.sync()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.agents(), self.rules())
        self.assertEqual(self.pin(), self.pinned)

    def test_update_takes_the_packs_latest_rules_and_keeps_the_repos_own_text(self):
        self.agents_md.write_text('# Repo\n\n' + self.agents_md.read_text() + '\nUse pnpm.\n')
        latest = self.share('Prefer small PRs.\nWrite tests first.\n')

        result = self.sync('update')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.agents(), '# Repo\n\n' + block('Prefer small PRs.\nWrite tests first.\n') + '\nUse pnpm.\n')
        self.assertEqual(self.pin(), latest)

    def test_ref_missing_from_the_origin_stops_the_sync_untouched(self):
        self.import_md().write_text(self.front('0' * 40))
        before = self.agents_md.read_text()

        result = self.sync()

        self.assertEqual(result.returncode, 1)
        self.assertIn('0' * 40, result.stderr)
        self.assertEqual(self.agents_md.read_text(), before)

    def test_import_pack_from_git_without_a_ref_stops_the_sync_untouched(self):
        self.import_md().write_text(f'---\nfrom: {self.origin}\npath: context\n---\n')
        before = self.agents_md.read_text()

        result = self.sync()

        self.assertEqual(result.returncode, 1)
        self.assertIn('context-packs/house-rules/pack.md', result.stderr)
        self.assertIn('ref', result.stderr)
        self.assertEqual(self.agents_md.read_text(), before)

    def test_update_with_a_ref_pins_the_pack_there(self):
        self.share('Prefer small PRs.\nWrite tests first.\n')
        self.tag('v1.0.0')

        result = self.sync('update', 'house-rules', '--ref', 'v1.0.0')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.agents(), block('Prefer small PRs.\nWrite tests first.\n'))
        self.assertEqual(self.pin(), 'v1.0.0')

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

    def test_add_with_a_tag_pins_the_pack_to_the_tag(self):
        self.assertEqual(self.agents(), self.rules())
        self.assertEqual(self.pin(), 'v1.2.0')

    def test_update_moves_to_the_newest_release_in_the_series(self):
        self.share('Prefer small PRs.\nWrite tests first.\n')
        self.tag('v1.9.0')
        self.tag('v1.10.0')
        self.share('Prefer tiny PRs.\n')
        self.tag('v2.0.0-rc1')
        self.tag('acme-v9.0.0')

        result = self.sync('update')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.agents(), block('Prefer small PRs.\nWrite tests first.\n'))
        self.assertEqual(self.pin(), 'v1.10.0')

    def test_update_keeps_the_tag_when_no_release_is_newer(self):
        self.share('Prefer tiny PRs.\n')

        result = self.sync('update')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.agents(), self.rules())
        self.assertEqual(self.pin(), 'v1.2.0')


class SeveralPacksTests(SyncCase):
    def setUp(self):
        super().setUp()
        self.share('Prefer small PRs.\n')
        self.add()
        self.acme_origin, self.acme = self.remote('acme')
        self.acme_ref = self.publish({'pack.md': 'Use acme.\n', 'deploy.md': doc('Deploying', 'Ship it.\n')},
                                     checkout=self.acme, folder='plugins/x')

    def add_acme(self, *args):
        return self.sync('add', 'acme', str(self.acme_origin), '--path', 'plugins/x', *args)

    def test_packs_render_in_the_order_of_their_folders(self):
        result = self.add_acme()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.agents(),
                         block('Use acme.\n\n## acme context\n\n| When | Read |\n|---|---|\n'
                               '| Deploying | `context-packs/gen/acme/deploy.md` |\n\nPrefer small PRs.\n'))
        self.assertEqual((self.gen / 'acme' / 'deploy.md').read_text(), doc('Deploying', 'Ship it.\n'))

    def test_update_moves_every_pinned_pack(self):
        self.add_acme()
        latest = self.share('Prefer small PRs.\nWrite tests first.\n')
        acme_latest = self.publish({'pack.md': 'Use acme v2.\n'}, checkout=self.acme, folder='plugins/x')

        result = self.sync('update')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Use acme v2.\n', self.agents())
        self.assertEqual(self.pin(), latest)
        self.assertEqual(self.pin('acme'), acme_latest)

    def test_update_by_id_moves_only_that_pack(self):
        self.add_acme()
        self.share('Prefer small PRs.\nWrite tests first.\n')
        acme_latest = self.publish({'pack.md': 'Use acme v2.\n'}, checkout=self.acme, folder='plugins/x')

        result = self.sync('update', 'acme')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.pin(), git(self.source, 'rev-parse', 'HEAD~1'))
        self.assertEqual(self.pin('acme'), acme_latest)

    def test_list_shows_every_import_pack_without_the_packs_nested_in_them(self):
        acme_ref = self.publish({'billing/pack.md': doc('Editing billing', 'Charge once.\n')},
                                checkout=self.acme, folder='plugins/x')
        self.add_acme()

        result = self.sync('list')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout,
                         f'acme  {self.acme_origin}  plugins/x @ {acme_ref}\n'
                         f'house-rules  {self.origin}  context @ {git(self.source, "rev-parse", "HEAD")}\n')


if __name__ == '__main__':
    unittest.main()
