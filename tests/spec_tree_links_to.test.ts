import assert from 'node:assert/strict';
import { describe, test } from 'node:test';

import { SMALL, TreeCase } from './tree_case.ts';

/** `trees.ts links-to <id>` lists the nodes that link to an ID, in every tree. */
describe('links-to', () => {
  test('lists each node that links to the id', async (t) => {
    const c = await TreeCase.make(t);
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
    const c = await TreeCase.make(t);
    c.write('review.tree.md', SMALL);

    const result = await c.trees('links-to', 'findres');

    assert.deepEqual([result.status, result.stderr], [1, 'trees.ts: no node has the ID findres\n']);
  });

  test('lists a link with display text', async (t) => {
    const c = await TreeCase.make(t);
    c.write('review.tree.md', SMALL.replace('see [[finders]]', 'by the [[finders|finders]]'));

    const result = await c.trees('links-to', 'finders');

    assert.deepEqual(
      [result.status, result.stdout],
      [0, 'review.tree.md: The author decides each finding, by the ' + '[[finders|finders]]\n'],
    );
  });
});
