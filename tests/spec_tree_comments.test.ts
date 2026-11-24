import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { describe, test } from 'node:test';

// The page's pure comment logic is a module, so its tests import it, as the page does.
import { asMarkdown, placeComments } from '../skills/spec-tree/scripts/tree_comments.mjs';
import { exits, includes } from './expect.ts';
import { run } from './scripts.ts';
import { SMALL, TreeCase } from './tree_case.ts';

/** A tree case that renders its tree and reads the page. */
class AnchorCase extends TreeCase {
  async render(file = 'review.tree.md'): Promise<string> {
    const result = await this.trees('render', file);
    exits(result, 0);
    return this.read(file.replace(/\.md$/, '.html'));
  }
}

/** The page gives the comment script what it anchors a comment on: each node's source text, and the tree's file. */
describe('CommentAnchorTests', () => {
  test('each node carries its source text without its id', async (t) => {
    const c = new AnchorCase(t);
    c.write('review.tree.md', SMALL.replace('Finders check the diff', 'Finders check `the diff` & "more"'));

    const page = await c.render();

    includes(page, '<li class="branch" id="finders" data-src="Finders check `the diff` &amp; &quot;more&quot;"');
    includes(page, '<li class="leaf row" tabindex="-1" data-src="Why: one finder per unit reads each file whole"');
  });

  test('each node carries the text it shows for a person to read', async (t) => {
    const c = new AnchorCase(t);
    c.write(
      'review.tree.md',
      SMALL.replace(
        'Why: one finder per unit reads each file whole',
        'Why: [[finders|a finder]] reads `a.py` & **each** [file](a.md), see [[finders]] and [[gone]]',
      ),
    );

    const page = await c.render();

    includes(
      page,
      'data-src="Why: [[finders|a finder]] reads `a.py` &amp; **each** [file](a.md), see [[finders]] ' +
        'and [[gone]]" data-text="Why: a finder reads a.py &amp; each file, see finders and gone">',
    );
  });

  test('the page names its tree file from the repo root', async (t) => {
    const c = new AnchorCase(t);
    c.write('review/review.tree.md', SMALL);

    const page = await c.render('review/review.tree.md');

    includes(page, '<main data-tree="review/review.tree.md">');
  });

  test('each page script parses', async (t) => {
    const c = new AnchorCase(t);
    c.write('review.tree.md', SMALL);
    const scripts = [...(await c.render()).matchAll(/<script type="module">([\s\S]*?)<\/script>/g)].map((m) => m[1]!);
    assert.equal(scripts.length, 2);

    for (const [i, script] of scripts.entries()) {
      const file = path.join(c.root, `page${i}.mjs`);
      fs.writeFileSync(file, script);
      const result = await run(['node', '--check', file], { cwd: c.root });
      exits(result, 0);
    }
  });
});

function comment(id: string, ...rest: string[]) {
  return { id, path: rest, text: 'Why?' };
}

function said(id: string, text: string, ...rest: string[]) {
  return { id, path: rest, text };
}

/** The page's pure comment logic: matching stored comments to nodes, and the Markdown copied for an agent. */
describe('CommentLogicTests', () => {
  test('places each comment on the node with its path', () => {
    const [a, b] = [comment('1', 'Top', 'Child'), comment('2', 'Top')];
    const paths = [['Top'], ['Top', 'Child'], ['Other']];

    assert.deepEqual(placeComments([a, b], paths), { byRow: [[b], [a], []], orphans: [] });
  });

  test('a comment whose path no node has is an orphan', () => {
    const gone = comment('1', 'Top', 'Old text');

    assert.deepEqual(placeComments([gone], [['Top'], ['Top', 'New text']]), { byRow: [[], []], orphans: [gone] });
  });

  test('two nodes with one path get the comment on the first', () => {
    const a = comment('1', 'Same');

    assert.deepEqual(placeComments([a], [['Same'], ['Same']]).byRow, [[a], []]);
  });

  test('markdown lists each comment with its node and ancestors', () => {
    const placed = [said('1', 'Too vague.', 'Top'), said('2', 'Line one\nLine two', 'Top', 'Why: "it" broke')];

    assert.equal(
      asMarkdown('review/review.tree.md', placed, []),
      'Comments on review/review.tree.md:\n' +
        '\n' +
        '1. On "Top":\n' +
        '   Too vague.\n' +
        '\n' +
        '2. On "Why: "it" broke", under "Top":\n' +
        '   Line one\n' +
        '   Line two\n',
    );
  });

  test('markdown lists orphans last and says why no node matched', () => {
    const placed = [comment('1', 'Top')];
    const orphans = [said('2', 'Still true?', 'A', 'B', 'Old text')];

    assert.equal(
      asMarkdown('review.tree.md', placed, orphans),
      'Comments on review.tree.md:\n' +
        '\n' +
        '1. On "Top":\n' +
        '   Why?\n' +
        '\n' +
        "These comments' nodes no longer match any node in review.tree.md, since a node's text or place changed " +
        'after the comment:\n' +
        '\n' +
        '2. On "Old text", under "A" > "B":\n' +
        '   Still true?\n',
    );
  });
});
