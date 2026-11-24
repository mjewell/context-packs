import assert from 'node:assert/strict';
import { describe, test } from 'node:test';

import { exits, includes } from './expect.ts';
import { block, doc, exists, HEADER, read, SyncCase } from './sync_case.ts';

/** The repo's own docs and rules, written in context-packs/ itself, and listed where they are. */
class RootCase extends SyncCase {
  protected override async setUp(): Promise<void> {
    await super.setUp();
    this.write('context-packs/project/deploy/index.md', doc('Deploying', 'Ship it.\n'));
    this.write('context-packs/project/design.md', doc('Changing the design', 'Keep it small.\n'));
  }
}

describe("the repo's own docs", () => {
  test('docs in context packs are listed where they are', async (t) => {
    const c = await RootCase.make(t);
    const result = await c.sync();

    exits(result, 0);
    assert.equal(
      c.agents(),
      block(
        '## Context\n\n| When | Read |\n|---|---|\n' +
          '| Deploying | `context-packs/project/deploy/index.md` |\n' +
          '| Changing the design | `context-packs/project/design.md` |\n',
      ),
    );
    assert.ok(!exists(c.gen));
  });

  test('pack md in context packs is inlined before its table', async (t) => {
    const c = await RootCase.make(t);
    c.write('context-packs/pack.md', 'Use pnpm.\n');

    const result = await c.sync();

    exits(result, 0);
    includes(c.agents(), `${HEADER}\nUse pnpm.\n\n## Context\n`);
  });

  test('when on the pack md in context packs stops the sync', async (t) => {
    const c = await RootCase.make(t);
    c.write('context-packs/pack.md', doc('Working on anything', 'Use pnpm.\n'));

    const result = await c.sync();

    exits(result, 1);
    includes(result.stderr, 'context-packs/pack.md');
    includes(result.stderr, 'when');
  });

  test('editing a doc needs no resync', async (t) => {
    const c = await RootCase.make(t);
    await c.sync();
    const before = read(c.agentsMd);
    c.write('context-packs/project/design.md', doc('Changing the design', 'Keep it smaller.\n'));

    const result = await c.sync();

    exits(result, 0);
    assert.equal(read(c.agentsMd), before);
  });

  test('new doc joins the table on resync', async (t) => {
    const c = await RootCase.make(t);
    await c.sync();
    c.write('context-packs/project/billing.md', doc('Editing billing', 'Charge once.\n'));

    const result = await c.sync();

    exits(result, 0);
    includes(c.agents(), '| Editing billing | `context-packs/project/billing.md` |\n');
  });
});
