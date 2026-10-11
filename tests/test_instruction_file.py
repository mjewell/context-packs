import os
import unittest

from test_cli import EMPTY_HEADER, HEADER, SyncCase


class InstructionFileTests(SyncCase):
    """Which file the sync writes: whichever of AGENTS.md and CLAUDE.md holds the blocks, else AGENTS.md or CLAUDE.md
    if one exists, else a new AGENTS.md with CLAUDE.md linked to it."""

    def setUp(self):
        super().setUp()
        self.agents_md = self.repo / 'AGENTS.md'
        self.claude_md = self.repo / 'CLAUDE.md'

    def test_claude_md_alone_is_synced_and_keeps_its_own_text(self):
        self.claude_md.write_text('# Repo\n\n' + EMPTY_HEADER + '\nUse named exports.\n')

        result = self.sync()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.claude_md.read_text(), '# Repo\n\n' + HEADER + '\nUse named exports.\n')
        self.assertFalse(os.path.lexists(self.agents_md))

    def test_pack_added_to_claude_md_resyncs_with_nothing_changed(self):
        self.share('Prefer small PRs.\n')
        self.claude_md.write_text(EMPTY_HEADER)
        self.add()

        result = self.sync()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.claude_md.read_text(), self.rules())
        self.assertTrue(result.stdout.startswith('Nothing changed: house-rules @ '), result.stdout)

    def test_claude_md_without_blocks_stops_and_shows_the_lines_to_add(self):
        self.claude_md.write_text('Old rules.\n')

        result = self.sync()

        self.assertEqual(result.returncode, 1)
        self.assertIn(f'{self.claude_md} has no context-packs blocks', result.stderr)
        self.assertIn(EMPTY_HEADER, result.stderr)
        self.assertEqual(sorted(p.name for p in self.repo.iterdir()), ['.git', 'CLAUDE.md'])
        self.assertEqual(self.claude_md.read_text(), 'Old rules.\n')

    def test_agents_md_is_synced_and_claude_md_left_alone(self):
        self.agents_md.write_text(EMPTY_HEADER)
        self.claude_md.write_text('@AGENTS.md\n')

        result = self.sync()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.agents_md.read_text(), HEADER)
        self.assertEqual(self.claude_md.read_text(), '@AGENTS.md\n')

    def test_existing_agents_md_gets_no_claude_md_link(self):
        self.agents_md.write_text(EMPTY_HEADER)

        result = self.sync()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(os.path.lexists(self.claude_md))

    def test_both_files_without_blocks_stop_and_leave_the_choice_to_the_repo(self):
        self.agents_md.write_text('Codex rules.\n')
        self.claude_md.write_text('Claude rules.\n')

        result = self.sync()

        self.assertEqual(result.returncode, 1)
        self.assertIn(f'Neither {self.agents_md} nor {self.claude_md} has context-packs blocks', result.stderr)
        self.assertIn(EMPTY_HEADER, result.stderr)
        self.assertEqual(self.agents_md.read_text(), 'Codex rules.\n')
        self.assertEqual(self.claude_md.read_text(), 'Claude rules.\n')

    def test_claude_md_holding_the_blocks_stays_the_one_synced_once_agents_md_appears(self):
        self.claude_md.write_text(EMPTY_HEADER)
        self.agents_md.write_text('Codex rules.\n')

        result = self.sync()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.claude_md.read_text(), HEADER)
        self.assertEqual(self.agents_md.read_text(), 'Codex rules.\n')

    def test_blocks_in_both_files_stop_the_sync_untouched(self):
        self.agents_md.write_text(EMPTY_HEADER)
        self.claude_md.write_text(EMPTY_HEADER)

        result = self.sync()

        self.assertEqual(result.returncode, 1)
        self.assertIn('AGENTS.md and', result.stderr)
        self.assertIn('CLAUDE.md both have context-packs blocks', result.stderr)
        self.assertEqual(self.agents_md.read_text(), EMPTY_HEADER)
        self.assertEqual(self.claude_md.read_text(), EMPTY_HEADER)

    def test_agents_md_linked_to_claude_md_syncs_claude_md(self):
        self.claude_md.write_text(EMPTY_HEADER)
        self.agents_md.symlink_to('CLAUDE.md')

        result = self.sync()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.claude_md.read_text(), HEADER)
        self.assertEqual(os.readlink(self.agents_md), 'CLAUDE.md')

    def test_claude_md_linked_elsewhere_stops_the_sync_untouched(self):
        target = self.source / 'old-rules.md'
        self.claude_md.symlink_to(target)

        result = self.sync()

        self.assertEqual(result.returncode, 1)
        self.assertIn(f'{self.claude_md} is a symlink', result.stderr)
        self.assertFalse(target.exists())
        self.assertFalse(os.path.lexists(self.agents_md))


if __name__ == '__main__':
    unittest.main()
