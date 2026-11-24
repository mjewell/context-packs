import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { describe, test } from 'node:test';

import { exits, includes } from './expect.ts';
import { command, ROOT, run } from './scripts.ts';
import { SMALL, TreeCase } from './tree_case.ts';

/** n distinct words, so a text's size is known without counting by hand. */
function words(n: number, start = 0): string {
  return Array.from({ length: n }, (_, i) => `w${start + i}`).join(' ');
}

/** A tree file whose root sentence is three words, with the given bullet lines under it. */
function tree(...bullets: string[]): string {
  return `# Sizes {#sizes}\n\nThree word root.\n\n${bullets.map((line) => `${line}\n`).join('')}`;
}

/** `trees.ts check` reads every tree in the repo, and fails on what the spec says CI fails on. */
describe('CheckTests', () => {
  test('passes a tree that follows the rules', async (t) => {
    const c = new TreeCase(t);
    c.write('review.tree.md', SMALL);

    const result = await c.trees('check');

    assert.deepEqual([result.status, result.stdout, result.stderr], [0, '', '']);
  });

  test('fails a link to an id no tree has', async (t) => {
    const c = new TreeCase(t);
    c.write('review.tree.md', SMALL.replace('[[finders]]', '[[findres]]'));

    const result = await c.trees('check');

    assert.equal(result.status, 1);
    assert.equal(
      result.stdout,
      'review.tree.md: fail: [[findres]] doesn\'t resolve, under "The author ' +
        'decides each finding, see [[findres]]"\n',
    );
  });

  test('fails a link with display text to an id no tree has', async (t) => {
    const c = new TreeCase(t);
    c.write('review.tree.md', SMALL.replace('see [[finders]]', 'by the [[findres|finders]]'));

    const result = await c.trees('check');

    assert.equal(result.status, 1);
    assert.equal(
      result.stdout,
      'review.tree.md: fail: [[findres]] doesn\'t resolve, under "The author ' +
        'decides each finding, by the [[findres…"\n',
    );
  });

  test('resolves a link into another tree', async (t) => {
    const c = new TreeCase(t);
    c.write('review.tree.md', SMALL.replace('[[finders]]', '[[packs]]'));
    c.write(
      'docs/packs.tree.md',
      `
            # Packs {#packs}

            A pack holds rules.

            - Each rule has a \`when\`
            `,
    );

    assert.equal((await c.trees('check')).stdout, '');
  });

  test('fails an id two nodes use', async (t) => {
    const c = new TreeCase(t);
    c.write('review.tree.md', SMALL);
    c.write(
      'docs/packs.tree.md',
      `
            # Packs {#packs}

            A pack holds rules.

            - Finders read the packs {#finders}
            `,
    );

    const result = await c.trees('check');

    assert.equal(result.status, 1);
    assert.equal(
      result.stdout,
      'review.tree.md: fail: {#finders} is also the ID of a node in ' + 'docs/packs.tree.md\n',
    );
  });

  test('fails a node with more than one id', async (t) => {
    const c = new TreeCase(t);
    c.write('review.tree.md', SMALL.replace('{#finders}', '{#finders #finder}'));

    const result = await c.trees('check');

    assert.equal(result.status, 1);
    includes(
      result.stdout,
      'review.tree.md: fail: a node has one ID, written {#slug}, under "Finders check the diff ' +
        '{#finders #finder}"\n',
    );
  });

  test('fails a label written any other way', async (t) => {
    const c = new TreeCase(t);
    for (const text of [
      'Rejected, since it was slow',
      'why: it was slow',
      '**Rejected:** a cron job',
      'Why - it was slow',
    ]) {
      c.write('review.tree.md', SMALL.replace('Why: one finder per unit reads each file whole', text));

      const result = await c.trees('check');

      assert.equal(result.status, 1, text);
      includes(result.stdout, `review.tree.md: fail: a label is written Why: or Rejected:, under "${text}"\n`);
    }
  });

  test('passes a node that only starts with a word like a label', async (t) => {
    const c = new TreeCase(t);
    c.write(
      'review.tree.md',
      SMALL.replace(
        'Why: one finder per unit reads each file whole',
        "Whyte's rule says one finder reads each file whole",
      ),
    );

    assert.equal((await c.trees('check')).stdout, '');
  });
});

/** `trees.ts check` warns when a size passes its target, and fails at 1.5 times it. */
describe('SizeTests', () => {
  test('warns on node text over 40 words', async (t) => {
    const c = new TreeCase(t);
    c.write('sizes.tree.md', tree(`- ${words(41)}`));

    const result = await c.trees('check');

    assert.deepEqual(
      [result.status, result.stdout],
      [
        0,
        'sizes.tree.md: warn: node text is 41 words (target ' +
          '40), under "w0 w1 w2 w3 w4 w5 w6 w7 w8 w9 w10 w11 w12 w13 w14…"\n',
      ],
    );
  });

  test('counts a links display text but not its slug', async (t) => {
    const c = new TreeCase(t);
    c.write('sizes.tree.md', tree(`- ${words(39)} [[sizes|w39 w40]] [[sizes]]`));

    const result = await c.trees('check');

    assert.deepEqual(
      [result.status, result.stdout],
      [
        0,
        'sizes.tree.md: warn: node text is 41 words (target ' +
          '40), under "w0 w1 w2 w3 w4 w5 w6 w7 w8 w9 w10 w11 w12 w13 w14…"\n',
      ],
    );
  });

  test('fails node text over 60 words', async (t) => {
    const c = new TreeCase(t);
    c.write('sizes.tree.md', tree(`- ${words(61)}`));

    const result = await c.trees('check');

    assert.equal(result.status, 1);
    includes(result.stdout, 'sizes.tree.md: fail: node text is 61 words (limit 60), under');
  });

  test('warns on more than 7 children', async (t) => {
    const c = new TreeCase(t);
    c.write('sizes.tree.md', tree(...Array.from({ length: 8 }, (_, i) => `- child ${i}`)));

    assert.equal(
      (await c.trees('check')).stdout,
      'sizes.tree.md: warn: has 8 children (target 7), under ' + '"Sizes"\n',
    );
  });

  test('warns on a view over 150 words', async (t) => {
    const c = new TreeCase(t);
    c.write('sizes.tree.md', tree(...Array.from({ length: 4 }, (_, i) => `- ${words(38, 38 * i)}`)));

    assert.equal(
      (await c.trees('check')).stdout,
      'sizes.tree.md: warn: view is 155 words (target 150), under ' + '"Sizes"\n',
    );
  });

  test('fails a view over 225 words', async (t) => {
    const c = new TreeCase(t);
    c.write('sizes.tree.md', tree(...Array.from({ length: 6 }, (_, i) => `- ${words(38, 38 * i)}`)));

    const result = await c.trees('check');

    assert.deepEqual(
      [result.status, result.stdout],
      [1, 'sizes.tree.md: fail: view is 231 words (limit 225), ' + 'under "Sizes"\n'],
    );
  });

  test('warns on a nested subtree of 60 words or fewer', async (t) => {
    const c = new TreeCase(t);
    c.write(
      'sizes.tree.md',
      tree('- parent node here', '  - child node', '    - grandchild node', `- ${words(38)}`, `- ${words(38, 38)}`),
    );

    assert.equal(
      (await c.trees('check')).stdout,
      'sizes.tree.md: warn: nested subtree is 7 words (flatten at ' + '60 or fewer), under "parent node here"\n',
    );
  });
});

/** `trees.ts stats` prints each view's size, child count and subtree size. */
describe('StatsTests', () => {
  test('prints sizes for each view', async (t) => {
    const c = new TreeCase(t);
    c.write('review.tree.md', SMALL);

    const result = await c.trees('stats');

    assert.deepEqual(
      [result.status, result.stdout],
      [0, 'Review: view 54, 3 children, subtree 62\n' + '  Finders check the diff: view 12, 1 child, subtree 12\n'],
    );
  });
});

/** A command given the wrong arguments says what it takes, and lists every command. */
describe('UsageTests', () => {
  test('says what a command takes and exits 2', async (t) => {
    const c = new TreeCase(t);
    for (const [args, says] of [
      [['render'], 'render takes <id>.tree.md [-o out.html]'],
      [['links-to', 'a', 'b'], 'links-to takes <id>'],
      [['stats', '-o', 'x'], 'stats takes no arguments'],
      [['publish'], "there's no command publish"],
      [[], 'name a command'],
    ] as const) {
      const result = await c.trees(...args);

      assert.equal(result.status, 2, `${args}: ${result.stderr}`);
      assert.equal(
        result.stderr,
        `trees.ts: ${says}.\n\n` +
          'Usage:\n' +
          '  trees.ts check\n' +
          '  trees.ts stats\n' +
          '  trees.ts links-to <id>\n' +
          '  trees.ts render <id>.tree.md [-o out.html]\n',
      );
    }
  });
});

/** `trees.ts links-to <id>` lists the nodes that link to an ID, in every tree. */
describe('LinksToTests', () => {
  test('lists each node that links to the id', async (t) => {
    const c = new TreeCase(t);
    c.write('review.tree.md', SMALL);
    c.write(
      'docs/packs.tree.md',
      `
            # Packs {#packs}

            A pack holds rules.

            - Each rule is checked by the finders, see [[finders]]
            `,
    );

    const result = await c.trees('links-to', 'finders');

    assert.deepEqual(
      [result.status, result.stdout],
      [
        0,
        'docs/packs.tree.md: Each rule is checked by the ' +
          'finders, see [[finders]]\n' +
          'review.tree.md: The author decides each finding, ' +
          'see [[finders]]\n',
      ],
    );
  });

  test('fails on an id no node has', async (t) => {
    const c = new TreeCase(t);
    c.write('review.tree.md', SMALL);

    const result = await c.trees('links-to', 'findres');

    assert.deepEqual([result.status, result.stderr], [1, 'trees.ts: no node has the ID findres\n']);
  });

  test('lists a link with display text', async (t) => {
    const c = new TreeCase(t);
    c.write('review.tree.md', SMALL.replace('see [[finders]]', 'by the [[finders|finders]]'));

    const result = await c.trees('links-to', 'finders');

    assert.deepEqual(
      [result.status, result.stdout],
      [0, 'review.tree.md: The author decides each finding, by the ' + '[[finders|finders]]\n'],
    );
  });
});

/** `trees.ts render` writes a tree's page beside its file. */
describe('RenderTests', () => {
  test('writes the page beside the tree file', async (t) => {
    const c = new TreeCase(t);
    c.write('review.tree.md', SMALL);

    const result = await c.trees('render', 'review.tree.md');

    exits(result, 0);
    includes(c.read('review.tree.html'), '<title>Review</title>');
  });

  test('renders a code span in a links display text', async (t) => {
    const c = new TreeCase(t);
    c.write('review.tree.md', SMALL.replace('see [[finders]]', 'when its [[finders|`when` <x>]] matches'));

    const result = await c.trees('render', 'review.tree.md');

    exits(result, 0);
    includes(
      c.read('review.tree.html'),
      'when its <a class="jump" href="#finders"><code>when</code> &lt;x&gt;</a> matches',
    );
  });

  test('leaves a link inside a code span as code', async (t) => {
    const c = new TreeCase(t);
    c.write('review.tree.md', SMALL.replace('see [[finders]]', 'written `[[finders|x]]`'));

    const result = await c.trees('render', 'review.tree.md');

    exits(result, 0);
    includes(c.read('review.tree.html'), 'written <code>[[finders|x]]</code>');
  });

  test('renders a links display text escaped', async (t) => {
    const c = new TreeCase(t);
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
    const c = new TreeCase(t);
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
    const c = new TreeCase(t);
    c.write('review.tree.md', SMALL.replace('{#finders}', '{#finders #finder}'));

    const result = await c.trees('render', 'review.tree.md');

    exits(result, 1);
    includes(result.stderr, 'a node has one ID, written {#slug}');
    assert.ok(!fs.existsSync(path.join(c.root, 'review.tree.html')));
  });

  test('escapes a quote in a links url', async (t) => {
    const c = new TreeCase(t);
    c.write('review.tree.md', SMALL.replace('see [[finders]]', 'see [docs](https://e.com/a"onclick=x)'));

    const result = await c.trees('render', 'review.tree.md');

    exits(result, 0);
    includes(c.read('review.tree.html'), '<a href="https://e.com/a&quot;onclick=x">docs</a>');
  });

  test('renders relative anchor http and mailto links', async (t) => {
    const c = new TreeCase(t);
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
    const c = new TreeCase(t);
    c.write('review.tree.md', SMALL.replace('see [[finders]]', 'see [docs](javascript:alert(1))'));

    const result = await c.trees('render', 'review.tree.md');

    exits(result, 1);
    includes(result.stderr, 'javascript:alert(1');
    assert.ok(!fs.existsSync(path.join(c.root, 'review.tree.html')));
  });

  test('refuses a link that starts with a control character', async (t) => {
    const c = new TreeCase(t);
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

/** `trees.ts render` holds a D2 diagram's links to the rule Markdown links follow. */
describe('D2RenderTests', { skip: HAS_D2 ? false : 'renders D2 diagrams through the d2 CLI' }, () => {
  test('renders a diagram with an https link', async (t) => {
    const c = new TreeCase(t);
    diagram(c, 'x.link: "https://e.com/docs"');

    const result = await c.trees('render', 'review.tree.md');

    exits(result, 0);
    includes(c.read('review.tree.html'), 'href="https://e.com/docs"');
  });

  test('refuses a diagram link to a url scheme that can run script', async (t) => {
    const c = new TreeCase(t);
    diagram(c, 'x.link: "javascript:alert(1)"');

    const result = await c.trees('render', 'review.tree.md');

    exits(result, 1);
    includes(result.stderr, 'javascript:alert(1)');
    assert.ok(!fs.existsSync(path.join(c.root, 'review.tree.html')));
  });
});

/** This repo's own trees follow the spec's rules, so the test suite checks them until a CI workflow does. */
describe('RepoTreesTests', () => {
  test('this repos trees have no failures', async () => {
    const result = await run([...command('skills/spec-tree/scripts/trees'), 'check'], { cwd: ROOT });

    assert.equal(result.status, 0, result.stdout + result.stderr);
  });
});
