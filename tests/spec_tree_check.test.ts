import assert from 'node:assert/strict';
import { describe, test } from 'node:test';

import { includes } from './expect.ts';
import { command, ROOT, run } from './scripts.ts';
import { SMALL, TreeCase, tree, words } from './tree_case.ts';

/** `trees.ts check` reads every tree in the repo, and fails on what the spec says CI fails on. */
describe('check', () => {
  test('passes a tree that follows the rules', async (t) => {
    const c = await TreeCase.make(t);
    c.write('review.tree.md', SMALL);

    const result = await c.trees('check');

    assert.deepEqual([result.status, result.stdout, result.stderr], [0, '', '']);
  });

  test('fails a link to an id no tree has', async (t) => {
    const c = await TreeCase.make(t);
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
    const c = await TreeCase.make(t);
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
    const c = await TreeCase.make(t);
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
    const c = await TreeCase.make(t);
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
    const c = await TreeCase.make(t);
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
    const c = await TreeCase.make(t);
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
    const c = await TreeCase.make(t);
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
describe('sizes', () => {
  test('warns on node text over 40 words', async (t) => {
    const c = await TreeCase.make(t);
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
    const c = await TreeCase.make(t);
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
    const c = await TreeCase.make(t);
    c.write('sizes.tree.md', tree(`- ${words(61)}`));

    const result = await c.trees('check');

    assert.equal(result.status, 1);
    includes(result.stdout, 'sizes.tree.md: fail: node text is 61 words (limit 60), under');
  });

  test('warns on more than 7 children', async (t) => {
    const c = await TreeCase.make(t);
    c.write('sizes.tree.md', tree(...Array.from({ length: 8 }, (_, i) => `- child ${i}`)));

    assert.equal(
      (await c.trees('check')).stdout,
      'sizes.tree.md: warn: has 8 children (target 7), under ' + '"Sizes"\n',
    );
  });

  test('warns on a view over 150 words', async (t) => {
    const c = await TreeCase.make(t);
    c.write('sizes.tree.md', tree(...Array.from({ length: 4 }, (_, i) => `- ${words(38, 38 * i)}`)));

    assert.equal(
      (await c.trees('check')).stdout,
      'sizes.tree.md: warn: view is 155 words (target 150), under ' + '"Sizes"\n',
    );
  });

  test('fails a view over 225 words', async (t) => {
    const c = await TreeCase.make(t);
    c.write('sizes.tree.md', tree(...Array.from({ length: 6 }, (_, i) => `- ${words(38, 38 * i)}`)));

    const result = await c.trees('check');

    assert.deepEqual(
      [result.status, result.stdout],
      [1, 'sizes.tree.md: fail: view is 231 words (limit 225), ' + 'under "Sizes"\n'],
    );
  });

  test('warns on a nested subtree of 60 words or fewer', async (t) => {
    const c = await TreeCase.make(t);
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

/** This repo's own trees follow the spec's rules, so the test suite checks them until a CI workflow does. */
describe("this repo's trees", () => {
  test('this repos trees have no failures', async () => {
    const result = await run([...command('skills/spec-tree/scripts/trees'), 'check'], { cwd: ROOT });

    assert.equal(result.status, 0, result.stdout + result.stderr);
  });
});
