import assert from 'node:assert/strict';
import { describe, test } from 'node:test';

import { TreeCase } from './tree_case.ts';

/** A command given the wrong arguments says what it takes, and lists every command. */
describe('usage', () => {
  test('says what a command takes and exits 2', async (t) => {
    const c = await TreeCase.make(t);
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
