import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { describe, test } from 'node:test';

import { exits, includes } from './expect.ts';
import { SMALL, TreeCase, tree } from './tree_case.ts';

/** `trees.ts render` writes a tree's page beside its file. */
describe('render', () => {
  test('writes the page beside the tree file', async (t) => {
    const c = await TreeCase.make(t);
    c.write('review.tree.md', SMALL);

    const result = await c.trees('render', 'review.tree.md');

    exits(result, 0);
    includes(c.read('review.tree.html'), '<title>Review</title>');
  });

  test('renders a code span in a links display text', async (t) => {
    const c = await TreeCase.make(t);
    c.write('review.tree.md', SMALL.replace('see [[finders]]', 'when its [[finders|`when` <x>]] matches'));

    const result = await c.trees('render', 'review.tree.md');

    exits(result, 0);
    includes(
      c.read('review.tree.html'),
      'when its <a class="jump" href="#finders"><code>when</code> &lt;x&gt;</a> matches',
    );
  });

  test('leaves a link inside a code span as code', async (t) => {
    const c = await TreeCase.make(t);
    c.write('review.tree.md', SMALL.replace('see [[finders]]', 'written `[[finders|x]]`'));

    const result = await c.trees('render', 'review.tree.md');

    exits(result, 0);
    includes(c.read('review.tree.html'), 'written <code>[[finders|x]]</code>');
  });

  test('renders a links display text escaped', async (t) => {
    const c = await TreeCase.make(t);
    c.write('review.tree.md', SMALL.replace('see [[finders]]', 'by [[finders|the <finders>]] and [[nope|x]]'));

    const result = await c.trees('render', 'review.tree.md');

    exits(result, 0);
    includes(
      c.read('review.tree.html'),
      'by <a class="jump" href="#finders">the &lt;finders&gt;</a> and ' +
        '<span class="jump missing" title="Not in this tree">x</span>',
    );
  });

  test('counts every node below a branch', async (t) => {
    const c = await TreeCase.make(t);
    c.write(
      'review.tree.md',
      tree('- Branch with two children and one grandchild', '  - Child', '    - Grandchild', '  - Child'),
    );

    const result = await c.trees('render', 'review.tree.md');

    exits(result, 0);
    const page = c.read('review.tree.html');
    includes(page, '<span class="count" title="3 nodes below">3</span>');
    includes(page, '<span class="count" title="1 node below">1</span>');
  });

  test('refuses a tree that doesnt read as a tree', async (t) => {
    const c = await TreeCase.make(t);
    c.write('review.tree.md', SMALL.replace('{#finders}', '{#finders #finder}'));

    const result = await c.trees('render', 'review.tree.md');

    exits(result, 1);
    includes(result.stderr, 'a node has one ID, written {#slug}');
    assert.ok(!fs.existsSync(path.join(c.root, 'review.tree.html')));
  });

  test('escapes a quote in a links url', async (t) => {
    const c = await TreeCase.make(t);
    c.write('review.tree.md', SMALL.replace('see [[finders]]', 'see [docs](https://e.com/a"onclick=x)'));

    const result = await c.trees('render', 'review.tree.md');

    exits(result, 0);
    includes(c.read('review.tree.html'), '<a href="https://e.com/a&quot;onclick=x">docs</a>');
  });

  test('renders relative anchor http and mailto links', async (t) => {
    const c = await TreeCase.make(t);
    const links = '[a](docs/review.md) [b](#finders) [c](HTTPS://e.com) [d](mailto:me@e.com)';
    c.write('review.tree.md', SMALL.replace('see [[finders]]', `see ${links}`));

    const result = await c.trees('render', 'review.tree.md');

    exits(result, 0);
    includes(
      c.read('review.tree.html'),
      '<a href="docs/review.md">a</a> <a href="#finders">b</a> <a href="HTTPS://e.com">c</a> ' +
        '<a href="mailto:me@e.com">d</a>',
    );
  });

  test('refuses a link to a url scheme that can run script', async (t) => {
    const c = await TreeCase.make(t);
    c.write('review.tree.md', SMALL.replace('see [[finders]]', 'see [docs](javascript:alert(1))'));

    const result = await c.trees('render', 'review.tree.md');

    exits(result, 1);
    includes(result.stderr, 'javascript:alert(1');
    assert.ok(!fs.existsSync(path.join(c.root, 'review.tree.html')));
  });

  test('refuses a link that starts with a control character', async (t) => {
    const c = await TreeCase.make(t);
    // Browsers drop a URL's leading control characters, so this one would still run as javascript:.
    c.write('review.tree.md', SMALL.replace('see [[finders]]', 'see [docs](\x01javascript:alert(1))'));

    const result = await c.trees('render', 'review.tree.md');

    exits(result, 1);
    assert.ok(!fs.existsSync(path.join(c.root, 'review.tree.html')));
  });
});

const HAS_D2 = spawnSync('d2', ['--version']).error === undefined;

/** A tree whose one node holds a D2 diagram of source. */
function diagram(c: TreeCase, source: string): void {
  c.write(
    'review.tree.md',
    `
            # Review {#review}

            A review checks a change against the repo's rules.

            - Finders check the diff {#finders}
              \`\`\`d2
              ${source}
              \`\`\`
            `,
  );
}

// Skipped one test at a time, since node:test counts no test in a skipped suite, and the run would never say they
// didn't run.
const D2 = { skip: HAS_D2 ? false : 'renders D2 diagrams through the d2 CLI' };

/** `trees.ts render` holds a D2 diagram's links to the rule Markdown links follow. */
describe('render with D2', () => {
  test('renders a diagram with an https link', D2, async (t) => {
    const c = await TreeCase.make(t);
    diagram(c, 'x.link: "https://e.com/docs"');

    const result = await c.trees('render', 'review.tree.md');

    exits(result, 0);
    includes(c.read('review.tree.html'), 'href="https://e.com/docs"');
  });

  test('refuses a diagram link to a url scheme that can run script', D2, async (t) => {
    const c = await TreeCase.make(t);
    diagram(c, 'x.link: "javascript:alert(1)"');

    const result = await c.trees('render', 'review.tree.md');

    exits(result, 1);
    includes(result.stderr, 'javascript:alert(1)');
    assert.ok(!fs.existsSync(path.join(c.root, 'review.tree.html')));
  });
});
