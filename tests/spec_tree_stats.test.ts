import assert from 'node:assert/strict';
import { describe, test } from 'node:test';

import { SMALL, TreeCase } from './tree_case.ts';

/** `trees.ts stats` prints each view's size, child count and subtree size. */
describe('stats', () => {
  test('prints sizes for each view', async (t) => {
    const c = await TreeCase.make(t);
    c.write('review.tree.md', SMALL);

    const result = await c.trees('stats');

    assert.deepEqual(
      [result.status, result.stdout],
      [0, 'Review: view 54, 3 children, subtree 62\n' + '  Finders check the diff: view 12, 1 child, subtree 12\n'],
    );
  });
});
