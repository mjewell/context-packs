import json
import re
import subprocess
import sys

from git_case import REVIEW, GitCase


class HandshakeTests(GitCase):
    """The server speaks MCP over stdio, so Claude Code can start it and list its tools."""

    def test_answers_initialize_and_lists_its_tools(self):
        server = self.server()

        self.assertEqual(server.initialized['protocolVersion'], '2025-06-18')
        self.assertIn('tools', server.initialized['capabilities'])
        tools = server.request('tools/list')['tools']
        self.assertEqual([tool['name'] for tool in tools], ['changed', 'diff', 'log'])
        for tool in tools:
            self.assertEqual(tool['inputSchema']['type'], 'object')
            self.assertFalse(tool['inputSchema']['additionalProperties'])

    def test_answers_a_ping_and_says_it_has_no_other_methods(self):
        server = self.server()

        self.assertEqual(server.request('ping'), {})
        self.assertEqual(server.request('resources/list')['code'], -32601)


class ChangedTests(GitCase):
    """changed() lists what the change touches, so the agent can pick what to read and how many pages each takes."""

    def test_lists_each_changed_path_with_the_lines_in_its_diff(self):
        self.commit('Add two files', {'a.txt': 'one\ntwo\nthree\n', 'docs/b.md': 'b\n'})
        self.commit('Change one', {'a.txt': 'one\n2\nthree\n'})

        # A new file's diff is six lines of header and a line for each line it holds.
        self.assertEqual(self.server().text('changed'), '9\ta.txt\n7\tdocs/b.md\n')

    def test_prints_the_head_lines_each_diff_shows_for_comments_on_them(self):
        self.commit('Add', {'a.txt': TWELVE, 'gone.txt': 'x\n'})
        self.base = self.git('rev-parse', 'HEAD')
        self.commit('Change line 10 and delete a file', {'a.txt': TWELVE.replace('l10\n', 'ten\n')},
                    removed=['gone.txt'])

        run = subprocess.run([sys.executable, str(REVIEW / 'git_server.py'), '--base', self.base, '--head', 'HEAD',
                              'shown'], cwd=self.repo, capture_output=True, text=True, check=True)

        self.assertEqual(json.loads(run.stdout), {'a.txt': [7, 8, 9, 10, 11, 12], 'gone.txt': []})

    def test_lists_a_rename_as_a_deleted_path_and_an_added_one(self):
        self.commit('Add', {'old.txt': 'x\n'})
        self.base = self.git('rev-parse', 'HEAD')
        self.git('mv', 'old.txt', 'new.txt')
        self.commit('Rename')

        self.assertEqual(self.server().text('changed'), '7\tnew.txt\n7\told.txt\n')


TWELVE = ''.join(f'l{n}\n' for n in range(1, 13))


def body(diff):
    """A diff from its first hunk on, without the header, whose index line holds hashes."""
    return diff[diff.index('@@'):]


class DiffTests(GitCase):
    """diff(path) shows one path's change, with each line the head has numbered as it is there, so a finding can
    name a line without counting."""

    def test_numbers_each_line_the_head_has_and_leaves_removed_lines_blank(self):
        self.commit('Add', {'a.txt': TWELVE})
        self.base = self.git('rev-parse', 'HEAD')
        self.commit('Change line 10', {'a.txt': TWELVE.replace('l10\n', 'ten\n')})

        diff = self.server().text('diff', path='a.txt')

        self.assertTrue(diff.startswith('diff --git a/a.txt b/a.txt\n'), diff)
        self.assertEqual(body(diff), '@@ -7,6 +7,6 @@ l6\n'
                                     ' 7  l7\n'
                                     ' 8  l8\n'
                                     ' 9  l9\n'
                                     '   -l10\n'
                                     '10 +ten\n'
                                     '11  l11\n'
                                     '12  l12\n')

    def test_numbers_each_hunk_from_its_own_start(self):
        self.commit('Add', {'a.txt': TWELVE})
        self.base = self.git('rev-parse', 'HEAD')
        self.commit('Change both ends', {'a.txt': 'one\n' + TWELVE[3:-4] + 'twelve\n'})

        self.assertEqual(body(self.server().text('diff', path='a.txt')), '@@ -1,4 +1,4 @@\n'
                                                                         '   -l1\n'
                                                                         ' 1 +one\n'
                                                                         ' 2  l2\n'
                                                                         ' 3  l3\n'
                                                                         ' 4  l4\n'
                                                                         '@@ -9,4 +9,4 @@ l8\n'
                                                                         ' 9  l9\n'
                                                                         '10  l10\n'
                                                                         '11  l11\n'
                                                                         '   -l12\n'
                                                                         '12 +twelve\n')

    def test_pads_the_numbers_to_the_widest_one_in_the_diff(self):
        self.commit('Add', {'a.txt': TWELVE})
        self.base = self.git('rev-parse', 'HEAD')
        self.commit('Change line 1', {'a.txt': 'one\n' + TWELVE[3:]})

        self.assertEqual(body(self.server().text('diff', path='a.txt')), '@@ -1,4 +1,4 @@\n'
                                                                         '  -l1\n'
                                                                         '1 +one\n'
                                                                         '2  l2\n'
                                                                         '3  l3\n'
                                                                         '4  l4\n')

    def test_leaves_the_no_newline_marker_unnumbered(self):
        self.commit('Add', {'a.txt': 'one\n'})
        self.base = self.git('rev-parse', 'HEAD')
        self.commit('Drop the newline', {'a.txt': 'one\ntwo'})

        self.assertEqual(body(self.server().text('diff', path='a.txt')), '@@ -1 +1,2 @@\n'
                                                                         '1  one\n'
                                                                         '2 +two\n'
                                                                         '  \\ No newline at end of file\n')

    def test_shows_only_the_change_since_the_merge_base(self):
        self.commit('Add', {'a.txt': 'a\n', 'b.txt': 'b\n'})
        fork = self.git('rev-parse', 'HEAD')
        self.git('checkout', '-q', '-b', 'base')
        self.base = self.commit('Change b on the base branch', {'b.txt': 'base\n'})
        self.git('checkout', '-q', fork)
        self.commit('Change a on the PR', {'a.txt': 'pr\n'})

        server = self.server()

        self.assertEqual(server.text('changed'), '7\ta.txt\n')
        self.assertEqual(server.call('diff', path='b.txt'), ("b.txt isn't one of the paths changed() lists.", True))


class PagingTests(GitCase):
    """Long output comes in pages of 1000 lines, so one call can't fill the agent's context."""

    def setUp(self):
        super().setUp()
        self.commit('Add a long file', {'long.txt': ''.join(f'{n}\n' for n in range(1, 2501))})

    def test_gives_the_first_page_and_says_how_to_get_the_next(self):
        text = self.server().text('diff', path='long.txt')

        lines = text.splitlines()
        self.assertEqual(len(lines), 1001)
        self.assertEqual(lines[999], ' 994 +994')
        self.assertEqual(lines[1000], '(page 1 of 3: call again with page 2 for more)')

    def test_gives_a_later_page(self):
        lines = self.server().text('diff', path='long.txt', page=3).splitlines()

        # The diff has 2506 lines: six of header, then one per line of the file.
        self.assertEqual(lines[0], '1995 +1995')
        self.assertEqual(lines[-2:], ['2500 +2500', '(page 3 of 3)'])

    def test_refuses_a_page_past_the_last(self):
        self.assertEqual(self.server().call('diff', path='long.txt', page=4),
                         ('long.txt has 3 pages.', True))


class CallTests(GitCase):
    """The server runs only its three tools, with arguments their schemas allow, and answers anything else with an
    error the agent can read, instead of stopping."""

    def setUp(self):
        super().setUp()
        self.commit('Add', {'a.txt': 'a\n'})

    def test_refuses_a_name_that_isnt_one_of_its_tools(self):
        server = self.server()

        for name in ('show', 'blame', 'file', 'paths', 'lines', '__init__', 'nope'):
            self.assertEqual(server.call(name), (f'There is no tool named {name}.', True))

    def test_refuses_arguments_its_schema_doesnt_allow(self):
        server = self.server()

        self.assertEqual(server.call('diff'), ('diff needs path.', True))
        self.assertEqual(server.call('diff', path='a.txt', color=True), ('diff takes no color.', True))
        self.assertEqual(server.call('diff', path=['a.txt']), ('diff needs path as a string.', True))
        self.assertEqual(server.call('diff', path='a.txt', page='2'), ('diff needs page as an integer.', True))
        self.assertEqual(server.call('diff', path='a.txt', page=True), ('diff needs page as an integer.', True))
        self.assertEqual(server.call('diff', path='a.txt', page=0), ('diff needs page to be at least 1.', True))
        self.assertEqual(server.text('changed'), '7\ta.txt\n')


class PathTests(GitCase):
    """A path is a path from the repo root, and git reads it as one: never as an option or a pattern."""

    def test_refuses_an_absolute_path_and_one_that_climbs_out(self):
        server = self.server()

        for path in ('/etc/passwd', '../a.txt', 'docs/../a.txt', '..', ''):
            self.assertEqual(server.call('diff', path=path),
                             (f'{path!r} must be a path from the repo root, without "..".', True))

    def test_reads_a_path_literally_not_as_a_pattern(self):
        self.commit('Add a file named like a pattern', {'*.txt': 'star\n', 'b.txt': 'b\n'})

        diff = self.server().text('diff', path='*.txt')

        self.assertIn('+star', diff)
        self.assertNotIn('b.txt', diff)


class LogTests(GitCase):
    """log() lists the change's commits with their messages, since a message can say a choice was deliberate."""

    def test_lists_the_changes_commits_newest_first_and_none_from_the_base_branch(self):
        self.commit('Add', {'a.txt': 'a\n'})
        fork = self.git('rev-parse', 'HEAD')
        self.git('checkout', '-q', '-b', 'base')
        self.base = self.commit('On the base branch', {'b.txt': 'b\n'})
        self.git('checkout', '-q', fork)
        first = self.commit('Change a\n\nThe reason.', {'a.txt': 'x\n'})
        second = self.commit('Add c', {'c.txt': 'c\n'})

        text = self.server().text('log')

        self.assertEqual(re.findall(r'^commit (\w+)$', text, re.M), [second, first])
        self.assertIn('    Change a\n    \n    The reason.\n', text)
        self.assertNotIn('On the base branch', text)

    def test_lists_only_the_commits_that_touched_a_path(self):
        first = self.commit('Add a', {'a.txt': 'a\n'})
        self.commit('Add b', {'b.txt': 'b\n'})

        self.assertEqual(re.findall(r'^commit (\w+)$', self.server().text('log', path='a.txt'), re.M), [first])


class DriverTests(GitCase):
    """No diff driver runs, even one the runner's git config sets up, since a PR picks which driver a path gets in
    .gitattributes."""

    def test_runs_no_external_diff_or_textconv(self):
        script = self.repo.parent / f'{self.repo.name}-driver.sh'
        ran = self.repo.parent / f'{self.repo.name}-ran'
        script.write_text(f'#!/bin/sh\ntouch {ran}\necho converted\n')
        script.chmod(0o755)
        self.addCleanup(script.unlink)
        self.git('config', 'diff.external', str(script))
        self.git('config', 'diff.conv.textconv', str(script))
        self.commit('Add', {'.gitattributes': '*.txt diff=conv\n', 'a.txt': 'a\n'})
        self.commit('Change', {'a.txt': 'b\n'})

        self.server().text('diff', path='a.txt')

        self.assertFalse(ran.exists())
