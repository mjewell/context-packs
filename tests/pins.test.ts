import assert from 'node:assert/strict';
import fs from 'node:fs';
import { describe, test } from 'node:test';

import { exits, includes } from './expect.ts';
import { block, packed, read, SyncCase } from './sync_case.ts';

/** A pack added at its origin's latest commit, which is pinned. */
class PinningCase extends SyncCase {
  pinned = '';

  protected override async setUp(): Promise<void> {
    await super.setUp();
    this.pinned = this.share('Prefer small PRs.\n');
    await this.add();
  }
}

describe('pins', () => {
  test('plain resync keeps the pinned rules after the pack moves on', async (t) => {
    const c = await PinningCase.make(t);
    c.share('Prefer small PRs.\nWrite tests first.\n');

    const result = await c.sync();

    exits(result, 0);
    assert.equal(c.agents(), c.rules());
    assert.equal(c.pin(), c.pinned);
  });

  test('update takes the packs latest rules and keeps the repos own text', async (t) => {
    const c = await PinningCase.make(t);
    fs.writeFileSync(c.agentsMd, `# Repo\n\n${read(c.agentsMd)}\nUse pnpm.\n`);
    const latest = c.share('Prefer small PRs.\nWrite tests first.\n');

    const result = await c.sync('update');

    exits(result, 0);
    assert.equal(
      c.agents(),
      `# Repo\n\n${block(packed('house-rules', 'Prefer small PRs.\nWrite tests first.\n'))}\nUse pnpm.\n`,
    );
    assert.equal(c.pin(), latest);
  });

  test('ref missing from the origin stops the sync untouched', async (t) => {
    const c = await PinningCase.make(t);
    fs.writeFileSync(c.importMd(), c.front('0'.repeat(40)));
    const before = read(c.agentsMd);

    const result = await c.sync();

    exits(result, 1);
    includes(result.stderr, '0'.repeat(40));
    assert.equal(read(c.agentsMd), before);
  });

  test('import pack from git without a ref stops the sync untouched', async (t) => {
    const c = await PinningCase.make(t);
    fs.writeFileSync(c.importMd(), `---\nfrom: ${c.origin}\npath: context\n---\n`);
    const before = read(c.agentsMd);

    const result = await c.sync();

    exits(result, 1);
    includes(result.stderr, 'context-packs/house-rules/pack.md');
    includes(result.stderr, 'ref');
    assert.equal(read(c.agentsMd), before);
  });

  test('update with a ref pins the pack there', async (t) => {
    const c = await PinningCase.make(t);
    c.share('Prefer small PRs.\nWrite tests first.\n');
    c.tag('v1.0.0');

    const result = await c.sync('update', 'house-rules', '--ref', 'v1.0.0');

    exits(result, 0);
    assert.equal(c.agents(), block(packed('house-rules', 'Prefer small PRs.\nWrite tests first.\n')));
    assert.equal(c.pin(), 'v1.0.0');
  });

  test('update with a ref needs exactly one pack', async (t) => {
    const c = await PinningCase.make(t);
    const before = read(c.agentsMd);

    const result = await c.sync('update', '--ref', c.pinned);

    exits(result, 1);
    includes(result.stderr, 'one pack');
    assert.equal(read(c.agentsMd), before);
  });

  test('update of a pack not installed stops', async (t) => {
    const c = await PinningCase.make(t);
    const result = await c.sync('update', 'acme');

    exits(result, 1);
    includes(result.stderr, 'acme');
  });
});

/** A pack pinned to a tag stays there until a ref names somewhere else. */
class VersionCase extends SyncCase {
  protected override async setUp(): Promise<void> {
    await super.setUp();
    this.share('Prefer small PRs.\n');
    this.tag('v1.2.0');
    await this.add('--ref', 'v1.2.0');
  }
}

describe('a pack pinned to a tag', () => {
  test('add with a tag pins the pack to the tag', async (t) => {
    const c = await VersionCase.make(t);
    assert.equal(c.agents(), c.rules());
    assert.equal(c.pin(), 'v1.2.0');
  });

  test('update leaves the tag even when a newer release exists', async (t) => {
    const c = await VersionCase.make(t);
    c.share('Prefer small PRs.\nWrite tests first.\n');
    c.tag('v1.3.0');

    const result = await c.sync('update');

    exits(result, 0);
    assert.equal(c.agents(), c.rules());
    assert.equal(c.pin(), 'v1.2.0');
  });
});
