import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { describe, test } from 'node:test';

import { exits, includes } from './expect.ts';
import { doc, names, read, SyncCase } from './sync_case.ts';

/** check, which exits 1 when a sync would change anything, and writes nothing. */
describe('CheckTests', () => {
  test('synced repo passes silently', async (t) => {
    const c = new SyncCase(t);
    c.share('Prefer small PRs.\n');
    await c.add();
    const before = read(c.agentsMd);

    const result = await c.sync('check');

    exits(result, 0);
    assert.equal(result.stdout, '');
    assert.equal(read(c.agentsMd), before);
  });

  test('when changed without a resync fails naming the block', async (t) => {
    const c = new SyncCase(t);
    c.write('context-packs/testing.md', doc('Writing tests'));
    await c.sync();
    const before = read(c.agentsMd);
    c.write('context-packs/testing.md', doc('Writing or changing tests'));

    const result = await c.sync('check');

    exits(result, 1);
    includes(result.stderr, `${c.agentsMd}: the context-packs block is stale`);
    includes(result.stderr, 'npx context-packs');
    assert.equal(read(c.agentsMd), before);
  });

  test('ref edited without a resync fails naming the stale generated file', async (t) => {
    const c = new SyncCase(t);
    const old = c.publish({ 'pack.md': 'Prefer small PRs.\n', 'testing.md': doc('Writing tests', 'Use factories.\n') });
    await c.add();
    const fresh = c.publish({ 'testing.md': doc('Writing tests', 'Use fixtures.\n') });
    fs.writeFileSync(c.importMd(), read(c.importMd()).replace(old, fresh));
    const synced = path.join(c.gen, 'house-rules', 'testing.md');

    const result = await c.sync('check');

    exits(result, 1);
    includes(result.stderr, 'context-packs/gen/house-rules/testing.md');
    assert.equal(read(synced), doc('Writing tests', 'Use factories.\n'));
  });

  test('repo never synced fails creating nothing', async (t) => {
    const c = new SyncCase(t);
    const result = await c.sync('check');

    exits(result, 1);
    includes(result.stderr, `context-packs: ${c.agentsMd} doesn't exist`);
    assert.deepEqual(names(c.repo), ['.git']);
  });

  test('block edited in the repo fails untouched', async (t) => {
    const c = new SyncCase(t);
    c.share('Prefer small PRs.\n');
    await c.add();
    const edited = read(c.agentsMd).replace('small PRs', 'tiny PRs');
    fs.writeFileSync(c.agentsMd, edited);

    const result = await c.sync('check');

    exits(result, 1);
    includes(result.stderr, 'was edited');
    assert.equal(read(c.agentsMd), edited);
  });
});
