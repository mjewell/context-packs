import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOLS = REPO / 'skills' / 'design-trees' / 'scripts'

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
    """A repo in a temporary folder, with design trees written into it, and the trees CLI run from its root."""

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
        return subprocess.run([sys.executable, str(TOOLS / 'trees.py'), *args], cwd=self.root, capture_output=True,
                              text=True)


class CheckTests(TreeCase):
    """`trees.py check` reads every tree in the repo, and fails on what the spec says CI fails on."""

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


class SizeTests(TreeCase):
    """`trees.py check` warns when a size passes its target, and fails at 1.5 times it."""

    def test_warns_on_node_text_over_40_words(self):
        self.write('sizes.tree.md', tree(f'- {words(41)}'))

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
    """`trees.py stats` prints each view's size, child count and subtree size."""

    def test_prints_sizes_for_each_view(self):
        self.write('review.tree.md', SMALL)

        run = self.trees('stats')

        self.assertEqual((run.returncode, run.stdout), (0, 'Review: view 54, 3 children, subtree 62\n'
                                                           '  Finders check the diff: view 12, 1 child, subtree 12\n'))


class LinksToTests(TreeCase):
    """`trees.py links-to <id>` lists the nodes that link to an ID, in every tree."""

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

        self.assertEqual((run.returncode, run.stderr), (1, 'trees.py: no node has the ID findres\n'))


class RenderTests(TreeCase):
    """`trees.py render` writes a tree's page beside its file."""

    def test_writes_the_page_beside_the_tree_file(self):
        self.write('review.tree.md', SMALL)

        run = self.trees('render', 'review.tree.md')

        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn('<title>Review</title>', (self.root / 'review.tree.html').read_text())

    def test_refuses_a_tree_that_doesnt_read_as_a_tree(self):
        self.write('review.tree.md', SMALL.replace('{#finders}', '{#finders #finder}'))

        run = self.trees('render', 'review.tree.md')

        self.assertEqual(run.returncode, 1)
        self.assertIn('a node has one ID, written {#slug}', run.stderr)
        self.assertFalse((self.root / 'review.tree.html').exists())


class RepoTreesTests(unittest.TestCase):
    """This repo's own trees follow the spec's rules, so the test suite checks them until a CI workflow does."""

    def test_this_repos_trees_have_no_failures(self):
        run = subprocess.run([sys.executable, str(TOOLS / 'trees.py'), 'check'], cwd=REPO, capture_output=True,
                             text=True)

        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)


if __name__ == '__main__':
    unittest.main()
