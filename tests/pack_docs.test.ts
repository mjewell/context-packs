import assert from 'node:assert/strict';
import path from 'node:path';
import { describe, test } from 'node:test';

import { exits, includes } from './expect.ts';
import { block, doc, exists, packed, read, SyncCase } from './sync_case.ts';

describe("a pack's docs", () => {
  test('doc is copied and listed', async (t) => {
    const c = await SyncCase.make(t);
    c.publish({ 'billing.md': doc('Billing', 'Charge once.\n') });

    const result = await c.add();

    exits(result, 0);
    assert.equal(read(path.join(c.gen, 'house-rules', 'billing.md')), doc('Billing', 'Charge once.\n'));
    assert.equal(
      c.agents(),
      block(
        packed(
          'house-rules',
          '## house-rules context\n\n| When | Read |\n|---|---|\n' +
            '| Billing | `context-packs/gen/house-rules/billing.md` |\n',
        ),
      ),
    );
    assert.equal((await c.sync()).status, 0);
  });

  test('front matter key the tool doesnt know stops the sync', async (t) => {
    const c = await SyncCase.make(t);
    c.publish({ 'billing.md': doc('Billing', 'Charge once.\n', { owner: 'payments' }) });

    const result = await c.add();

    exits(result, 1);
    includes(result.stderr, 'context/billing.md');
    includes(result.stderr, 'owner');
    assert.ok(!exists(c.agentsMd));
    assert.ok(!exists(c.packs));
  });
});
