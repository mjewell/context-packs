import json
import re
import shutil
import subprocess
import unittest

from test_spec_tree import SMALL, TOOLS, TreeCase

COMMENTS = TOOLS / 'tree_comments.mjs'


class CommentAnchorTests(TreeCase):
    """The page gives the comment script what it anchors a comment on: each node's source text, and the tree's file."""

    def render(self, path='review.tree.md'):
        run = self.trees('render', path)
        self.assertEqual(run.returncode, 0, run.stderr)
        return (self.root / path).with_suffix('.html').read_text()

    def test_each_node_carries_its_source_text_without_its_id(self):
        self.write('review.tree.md', SMALL.replace('Finders check the diff', 'Finders check `the diff` & "more"'))

        page = self.render()

        self.assertIn('<li class="branch" id="finders" data-src="Finders check `the diff` &amp; &quot;more&quot;">',
                      page)
        self.assertIn('<li class="leaf row" tabindex="-1" data-src="Why: one finder per unit reads each file whole">',
                      page)

    def test_the_page_names_its_tree_file_from_the_repo_root(self):
        self.write('review/review.tree.md', SMALL)

        page = self.render('review/review.tree.md')

        self.assertIn('<main data-tree="review/review.tree.md">', page)

    @unittest.skipUnless(shutil.which('node'), 'parses the page scripts with node')
    def test_each_page_script_parses(self):
        self.write('review.tree.md', SMALL)
        scripts = re.findall(r'<script type="module">(.*?)</script>', self.render(), re.DOTALL)
        self.assertEqual(len(scripts), 2)

        for i, script in enumerate(scripts):
            (self.root / f'page{i}.mjs').write_text(script)
            run = subprocess.run(['node', '--check', str(self.root / f'page{i}.mjs')], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)


def comment(id, *path, text='Why?'):
    return {'id': id, 'path': list(path), 'text': text}


@unittest.skipUnless(shutil.which('node'), 'runs the comment script under node')
class CommentLogicTests(unittest.TestCase):
    """The page's pure comment logic: matching stored comments to nodes, and the Markdown copied for an agent."""

    def call(self, name, *args):
        js = (f'import {{ {name} }} from {json.dumps(COMMENTS.as_uri())};'
              f'console.log(JSON.stringify({name}(...{json.dumps(args)})));')
        run = subprocess.run(['node', '--input-type=module', '-e', js], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        return json.loads(run.stdout)

    def test_places_each_comment_on_the_node_with_its_path(self):
        a, b = comment('1', 'Top', 'Child'), comment('2', 'Top')
        paths = [['Top'], ['Top', 'Child'], ['Other']]

        self.assertEqual(self.call('placeComments', [a, b], paths), {'byRow': [[b], [a], []], 'orphans': []})

    def test_a_comment_whose_path_no_node_has_is_an_orphan(self):
        gone = comment('1', 'Top', 'Old text')

        self.assertEqual(self.call('placeComments', [gone], [['Top'], ['Top', 'New text']]),
                         {'byRow': [[], []], 'orphans': [gone]})

    def test_two_nodes_with_one_path_get_the_comment_on_the_first(self):
        a = comment('1', 'Same')

        self.assertEqual(self.call('placeComments', [a], [['Same'], ['Same']])['byRow'], [[a], []])

    def test_markdown_lists_each_comment_with_its_node_and_ancestors(self):
        placed = [comment('1', 'Top', text='Too vague.'),
                  comment('2', 'Top', 'Why: "it" broke', text='Line one\nLine two')]

        self.assertEqual(self.call('asMarkdown', 'review/review.tree.md', placed, []), (
            'Comments on review/review.tree.md:\n'
            '\n'
            '1. On "Top":\n'
            '   Too vague.\n'
            '\n'
            '2. On "Why: "it" broke", under "Top":\n'
            '   Line one\n'
            '   Line two\n'))

    def test_markdown_lists_orphans_last_and_says_why_no_node_matched(self):
        placed, orphans = [comment('1', 'Top')], [comment('2', 'A', 'B', 'Old text', text='Still true?')]

        self.assertEqual(self.call('asMarkdown', 'review.tree.md', placed, orphans), (
            'Comments on review.tree.md:\n'
            '\n'
            '1. On "Top":\n'
            '   Why?\n'
            '\n'
            "These comments' nodes no longer match any node in review.tree.md, since a node's text or place changed "
            'after the comment:\n'
            '\n'
            '2. On "Old text", under "A" > "B":\n'
            '   Still true?\n'))


if __name__ == '__main__':
    unittest.main()
