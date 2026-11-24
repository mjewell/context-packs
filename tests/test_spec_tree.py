import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

from scripts import command

REPO = Path(__file__).resolve().parent.parent
TOOLS = REPO / 'skills' / 'spec-tree' / 'scripts'

SMALL = '''
    # Review {#review}

    A review checks a change against the repo's rules.

    - Finders check the diff {#finders}
      - Why: one finder per unit reads each file whole
    - The author decides each finding, see [[finders]]
    - A merge turns the finders' answers into one list of findings, writing one finding for each choice in the diff, however many rules from however many units flag that same choice at the same spots
    '''


def words(n, start=0):
    """n distinct words, so a text's size is known without counting by hand."""
    return ' '.join(f'w{i}' for i in range(start, start + n))


def tree(*bullets):
    """A tree file whose root sentence is three words, with the given bullet lines under it."""
    return '# Sizes {#sizes}\n\nThree word root.\n\n' + ''.join(line + '\n' for line in bullets)


class TreeCase(unittest.TestCase):
    """A repo in a temporary folder, with spec trees written into it, and the trees CLI run from its root."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / '.git').mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, path, text):
        file = self.root / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(textwrap.dedent(text).lstrip(), encoding='utf-8')

    def trees(self, *args):
        return subprocess.run([*command('skills/spec-tree/scripts/trees'), *args], cwd=self.root, capture_output=True,
                              text=True)


class CheckTests(TreeCase):
    """`trees.ts check` reads every tree in the repo, and fails on what the spec says CI fails on."""

    def test_passes_a_tree_that_follows_the_rules(self):
        self.write('review.tree.md', SMALL)

        run = self.trees('check')

        self.assertEqual((run.returncode, run.stdout, run.stderr), (0, '', ''))

    def test_fails_a_link_to_an_id_no_tree_has(self):
        self.write('review.tree.md', SMALL.replace('[[finders]]', '[[findres]]'))

        run = self.trees('check')

        self.assertEqual(run.returncode, 1)
        self.assertEqual(run.stdout, 'review.tree.md: fail: [[findres]] doesn\'t resolve, under "The author '
                                     'decides each finding, see [[findres]]"\n')

    def test_fails_a_link_with_display_text_to_an_id_no_tree_has(self):
        self.write('review.tree.md', SMALL.replace('see [[finders]]', 'by the [[findres|finders]]'))

        run = self.trees('check')

        self.assertEqual(run.returncode, 1)
        self.assertEqual(run.stdout, 'review.tree.md: fail: [[findres]] doesn\'t resolve, under "The author '
                                     'decides each finding, by the [[findres…"\n')

    def test_resolves_a_link_into_another_tree(self):
        self.write('review.tree.md', SMALL.replace('[[finders]]', '[[packs]]'))
        self.write('docs/packs.tree.md', '''
            # Packs {#packs}

            A pack holds rules.

            - Each rule has a `when`
            ''')

        self.assertEqual(self.trees('check').stdout, '')

    def test_fails_an_id_two_nodes_use(self):
        self.write('review.tree.md', SMALL)
        self.write('docs/packs.tree.md', '''
            # Packs {#packs}

            A pack holds rules.

            - Finders read the packs {#finders}
            ''')

        run = self.trees('check')

        self.assertEqual(run.returncode, 1)
        self.assertEqual(run.stdout, 'review.tree.md: fail: {#finders} is also the ID of a node in '
                                     'docs/packs.tree.md\n')







    def test_fails_a_node_with_more_than_one_id(self):
        self.write('review.tree.md', SMALL.replace('{#finders}', '{#finders #finder}'))

        run = self.trees('check')

        self.assertEqual(run.returncode, 1)
        self.assertIn('review.tree.md: fail: a node has one ID, written {#slug}, under "Finders check the diff '
                      '{#finders #finder}"\n', run.stdout)


    def test_fails_a_label_written_any_other_way(self):
        for text in ('Rejected, since it was slow', 'why: it was slow', '**Rejected:** a cron job', 'Why - it was slow'):
            with self.subTest(text=text):
                self.write('review.tree.md', SMALL.replace('Why: one finder per unit reads each file whole', text))

                run = self.trees('check')

                self.assertEqual(run.returncode, 1)
                self.assertIn(f'review.tree.md: fail: a label is written Why: or Rejected:, under "{text}"\n', run.stdout)

    def test_passes_a_node_that_only_starts_with_a_word_like_a_label(self):
        self.write('review.tree.md', SMALL.replace('Why: one finder per unit reads each file whole',
                                                   'Whyte\'s rule says one finder reads each file whole'))

        self.assertEqual(self.trees('check').stdout, '')

class SizeTests(TreeCase):
    """`trees.ts check` warns when a size passes its target, and fails at 1.5 times it."""

    def test_warns_on_node_text_over_40_words(self):
        self.write('sizes.tree.md', tree(f'- {words(41)}'))

        run = self.trees('check')

        self.assertEqual((run.returncode, run.stdout), (0, 'sizes.tree.md: warn: node text is 41 words (target '
                                                           '40), under "w0 w1 w2 w3 w4 w5 w6 w7 w8 w9 w10 w11 w12 w13 w14…"\n'))

    def test_counts_a_links_display_text_but_not_its_slug(self):
        self.write('sizes.tree.md', tree(f'- {words(39)} [[sizes|w39 w40]] [[sizes]]'))

        run = self.trees('check')

        self.assertEqual((run.returncode, run.stdout), (0, 'sizes.tree.md: warn: node text is 41 words (target '
                                                           '40), under "w0 w1 w2 w3 w4 w5 w6 w7 w8 w9 w10 w11 w12 w13 w14…"\n'))

    def test_fails_node_text_over_60_words(self):
        self.write('sizes.tree.md', tree(f'- {words(61)}'))

        run = self.trees('check')

        self.assertEqual(run.returncode, 1)
        self.assertIn('sizes.tree.md: fail: node text is 61 words (limit 60), under', run.stdout)

    def test_warns_on_more_than_7_children(self):
        self.write('sizes.tree.md', tree(*(f'- child {i}' for i in range(8))))

        self.assertEqual(self.trees('check').stdout, 'sizes.tree.md: warn: has 8 children (target 7), under '
                                                     '"Sizes"\n')

    def test_warns_on_a_view_over_150_words(self):
        self.write('sizes.tree.md', tree(*(f'- {words(38, 38 * i)}' for i in range(4))))

        self.assertEqual(self.trees('check').stdout, 'sizes.tree.md: warn: view is 155 words (target 150), under '
                                                     '"Sizes"\n')

    def test_fails_a_view_over_225_words(self):
        self.write('sizes.tree.md', tree(*(f'- {words(38, 38 * i)}' for i in range(6))))

        run = self.trees('check')

        self.assertEqual((run.returncode, run.stdout), (1, 'sizes.tree.md: fail: view is 231 words (limit 225), '
                                                           'under "Sizes"\n'))

    def test_warns_on_a_nested_subtree_of_60_words_or_fewer(self):
        self.write('sizes.tree.md', tree('- parent node here', '  - child node', '    - grandchild node',
                                               f'- {words(38)}', f'- {words(38, 38)}'))

        self.assertEqual(self.trees('check').stdout, 'sizes.tree.md: warn: nested subtree is 7 words (flatten at '
                                                     '60 or fewer), under "parent node here"\n')




class StatsTests(TreeCase):
    """`trees.ts stats` prints each view's size, child count and subtree size."""

    def test_prints_sizes_for_each_view(self):
        self.write('review.tree.md', SMALL)

        run = self.trees('stats')

        self.assertEqual((run.returncode, run.stdout), (0, 'Review: view 54, 3 children, subtree 62\n'
                                                           '  Finders check the diff: view 12, 1 child, subtree 12\n'))


class UsageTests(TreeCase):
    """A command given the wrong arguments says what it takes, and lists every command."""

    def test_says_what_a_command_takes_and_exits_2(self):
        for args, says in ((('render',), 'render takes <id>.tree.md [-o out.html]'),
                           (('links-to', 'a', 'b'), 'links-to takes <id>'),
                           (('stats', '-o', 'x'), 'stats takes no arguments'),
                           (('publish',), "there's no command publish"),
                           ((), 'name a command')):
            with self.subTest(args=args):
                run = self.trees(*args)

                self.assertEqual(run.returncode, 2, run.stderr)
                self.assertEqual(run.stderr, f'trees.ts: {says}.\n\n'
                                             'Usage:\n'
                                             '  trees.ts check\n'
                                             '  trees.ts stats\n'
                                             '  trees.ts links-to <id>\n'
                                             '  trees.ts render <id>.tree.md [-o out.html]\n')


class LinksToTests(TreeCase):
    """`trees.ts links-to <id>` lists the nodes that link to an ID, in every tree."""

    def test_lists_each_node_that_links_to_the_id(self):
        self.write('review.tree.md', SMALL)
        self.write('docs/packs.tree.md', '''
            # Packs {#packs}

            A pack holds rules.

            - Each rule is checked by the finders, see [[finders]]
            ''')

        run = self.trees('links-to', 'finders')

        self.assertEqual((run.returncode, run.stdout), (0, 'docs/packs.tree.md: Each rule is checked by the '
                                                           'finders, see [[finders]]\n'
                                                           'review.tree.md: The author decides each finding, '
                                                           'see [[finders]]\n'))

    def test_fails_on_an_id_no_node_has(self):
        self.write('review.tree.md', SMALL)

        run = self.trees('links-to', 'findres')

        self.assertEqual((run.returncode, run.stderr), (1, 'trees.ts: no node has the ID findres\n'))

    def test_lists_a_link_with_display_text(self):
        self.write('review.tree.md', SMALL.replace('see [[finders]]', 'by the [[finders|finders]]'))

        run = self.trees('links-to', 'finders')

        self.assertEqual((run.returncode, run.stdout), (0, 'review.tree.md: The author decides each finding, by the '
                                                           '[[finders|finders]]\n'))


class RenderTests(TreeCase):
    """`trees.ts render` writes a tree's page beside its file."""

    def test_writes_the_page_beside_the_tree_file(self):
        self.write('review.tree.md', SMALL)

        run = self.trees('render', 'review.tree.md')

        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn('<title>Review</title>', (self.root / 'review.tree.html').read_text())

    def test_renders_a_code_span_in_a_links_display_text(self):
        self.write('review.tree.md', SMALL.replace('see [[finders]]', 'when its [[finders|`when` <x>]] matches'))

        run = self.trees('render', 'review.tree.md')

        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn('when its <a class="jump" href="#finders"><code>when</code> &lt;x&gt;</a> matches',
                      (self.root / 'review.tree.html').read_text())

    def test_leaves_a_link_inside_a_code_span_as_code(self):
        self.write('review.tree.md', SMALL.replace('see [[finders]]', 'written `[[finders|x]]`'))

        run = self.trees('render', 'review.tree.md')

        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn('written <code>[[finders|x]]</code>', (self.root / 'review.tree.html').read_text())

    def test_renders_a_links_display_text_escaped(self):
        self.write('review.tree.md', SMALL.replace('see [[finders]]', 'by [[finders|the <finders>]] and [[nope|x]]'))

        run = self.trees('render', 'review.tree.md')

        self.assertEqual(run.returncode, 0, run.stderr)
        page = (self.root / 'review.tree.html').read_text()
        self.assertIn('by <a class="jump" href="#finders">the &lt;finders&gt;</a> and '
                      '<span class="jump missing" title="Not in this tree">x</span>', page)

    def test_counts_every_node_below_a_branch(self):
        self.write('review.tree.md', tree(
            '- Branch with two children and one grandchild',
            '  - Child',
            '    - Grandchild',
            '  - Child',
        ))

        run = self.trees('render', 'review.tree.md')

        self.assertEqual(run.returncode, 0, run.stderr)
        page = (self.root / 'review.tree.html').read_text()
        self.assertIn('<span class="count" title="3 nodes below">3</span>', page)
        self.assertIn('<span class="count" title="1 node below">1</span>', page)

    def test_refuses_a_tree_that_doesnt_read_as_a_tree(self):
        self.write('review.tree.md', SMALL.replace('{#finders}', '{#finders #finder}'))

        run = self.trees('render', 'review.tree.md')

        self.assertEqual(run.returncode, 1)
        self.assertIn('a node has one ID, written {#slug}', run.stderr)
        self.assertFalse((self.root / 'review.tree.html').exists())

    def test_escapes_a_quote_in_a_links_url(self):
        self.write('review.tree.md', SMALL.replace('see [[finders]]', 'see [docs](https://e.com/a"onclick=x)'))

        run = self.trees('render', 'review.tree.md')

        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn('<a href="https://e.com/a&quot;onclick=x">docs</a>', (self.root / 'review.tree.html').read_text())

    def test_renders_relative_anchor_http_and_mailto_links(self):
        links = '[a](docs/review.md) [b](#finders) [c](HTTPS://e.com) [d](mailto:me@e.com)'
        self.write('review.tree.md', SMALL.replace('see [[finders]]', 'see ' + links))

        run = self.trees('render', 'review.tree.md')

        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn('<a href="docs/review.md">a</a> <a href="#finders">b</a> <a href="HTTPS://e.com">c</a> '
                      '<a href="mailto:me@e.com">d</a>', (self.root / 'review.tree.html').read_text())

    def test_refuses_a_link_to_a_url_scheme_that_can_run_script(self):
        self.write('review.tree.md', SMALL.replace('see [[finders]]', 'see [docs](javascript:alert(1))'))

        run = self.trees('render', 'review.tree.md')

        self.assertEqual(run.returncode, 1)
        self.assertIn('javascript:alert(1', run.stderr)
        self.assertFalse((self.root / 'review.tree.html').exists())

    def test_refuses_a_link_that_starts_with_a_control_character(self):
        # Browsers drop a URL's leading control characters, so this one would still run as javascript:.
        self.write('review.tree.md', SMALL.replace('see [[finders]]', 'see [docs](\x01javascript:alert(1))'))

        run = self.trees('render', 'review.tree.md')

        self.assertEqual(run.returncode, 1)
        self.assertFalse((self.root / 'review.tree.html').exists())


@unittest.skipUnless(shutil.which('d2'), 'renders D2 diagrams through the d2 CLI')
class D2RenderTests(TreeCase):
    """`trees.ts render` holds a D2 diagram's links to the rule Markdown links follow."""

    def diagram(self, source):
        self.write('review.tree.md', f'''
            # Review {{#review}}

            A review checks a change against the repo's rules.

            - Finders check the diff {{#finders}}
              ```d2
              {source}
              ```
            ''')

    def test_renders_a_diagram_with_an_https_link(self):
        self.diagram('x.link: "https://e.com/docs"')

        run = self.trees('render', 'review.tree.md')

        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn('href="https://e.com/docs"', (self.root / 'review.tree.html').read_text())

    def test_refuses_a_diagram_link_to_a_url_scheme_that_can_run_script(self):
        self.diagram('x.link: "javascript:alert(1)"')

        run = self.trees('render', 'review.tree.md')

        self.assertEqual(run.returncode, 1)
        self.assertIn('javascript:alert(1)', run.stderr)
        self.assertFalse((self.root / 'review.tree.html').exists())


class RepoTreesTests(unittest.TestCase):
    """This repo's own trees follow the spec's rules, so the test suite checks them until a CI workflow does."""

    def test_this_repos_trees_have_no_failures(self):
        run = subprocess.run([*command('skills/spec-tree/scripts/trees'), 'check'], cwd=REPO, capture_output=True,
                             text=True)

        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)


if __name__ == '__main__':
    unittest.main()
