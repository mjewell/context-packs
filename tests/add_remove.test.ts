import assert from 'node:assert/strict';
import path from 'node:path';
import { describe, test } from 'node:test';

import { exits, includes } from './expect.ts';
import { block, doc, exists, packed, read, SyncCase } from './sync_case.ts';

/** A pack published to its origin, which the repo hasn't added yet. */
class AddRemoveCase extends SyncCase {
  first = '';

  protected override async setUp(): Promise<void> {
    await super.setUp();
    this.first = this.share('Prefer small PRs.\n');
  }
}

describe('add and remove', () => {
  test('add writes an import pack pinned to its origins latest commit', async (t) => {
    const c = await AddRemoveCase.make(t);
    const result = await c.add();

    exits(result, 0);
    assert.equal(read(c.importMd()), c.front(c.first));
    assert.equal(c.agents(), c.rules());
  });

  test('add with a ref pins the pack there', async (t) => {
    const c = await AddRemoveCase.make(t);
    c.share('Prefer small PRs.\nWrite tests first.\n');

    const result = await c.add('--ref', c.first.slice(0, 7));

    exits(result, 0);
    assert.equal(c.agents(), c.rules());
    assert.equal(c.pin(), c.first);
  });

  test('add with a branch as the ref stops untouched', async (t) => {
    const c = await AddRemoveCase.make(t);
    const result = await c.add('--ref', 'main');

    exits(result, 1);
    includes(result.stderr, 'branch');
    assert.ok(!exists(c.agentsMd));
    assert.ok(!exists(c.packs));
  });

  test('add where a folder already is stops untouched', async (t) => {
    const c = await AddRemoveCase.make(t);
    await c.add();
    const before = read(c.agentsMd);

    const result = await c.add();

    exits(result, 1);
    includes(result.stderr, 'context-packs/house-rules already exists');
    assert.equal(read(c.agentsMd), before);
  });

  test('add at a nested id writes the import pack there', async (t) => {
    const c = await AddRemoveCase.make(t);
    const result = await c.addAs('shared/house-rules');

    exits(result, 0);
    assert.equal(read(c.importMd('shared/house-rules')), c.front(c.first));
    assert.equal(c.agents(), block(packed('shared/house-rules', 'Prefer small PRs.\n')));
  });

  test('add of an id that isnt a folder under context packs stops', async (t) => {
    const c = await AddRemoveCase.make(t);
    for (const id of ['gen', '../rules', '.rules', 'a//b', '/rules']) {
      const result = await c.addAs(id);

      assert.equal(result.status, 1, id);
      includes(result.stderr, `${id} can't name a pack`, id);
      assert.ok(!exists(c.agentsMd), id);
    }
  });

  test('add of a folder in the repo imports it by its path alone', async (t) => {
    const c = await AddRemoveCase.make(t);
    c.write('team-rules/pack.md', 'Use pnpm.\n');

    for (const args of [['team-rules'], ['.', '--path', 'team-rules'], ['./docs/../team-rules']]) {
      const result = await c.sync('add', 'team', ...args);

      assert.equal(result.status, 0, `${args}: ${result.stderr}`);
      assert.equal(read(c.importMd('team')), '---\npath: team-rules\n---\n', `${args}`);
      assert.equal(c.agents(), block(packed('team', 'Use pnpm.\n')), `${args}`);
      await c.sync('remove', 'team');
    }
  });

  test('import pack whose path leaves the repo stops', async (t) => {
    const c = await AddRemoveCase.make(t);
    c.write('context-packs/team/pack.md', '---\npath: ../team-rules\n---\n');

    const result = await c.sync();

    exits(result, 1);
    includes(result.stderr, 'context-packs/team/pack.md');
    includes(result.stderr, 'outside');
    includes(result.stderr, 'from');
  });

  test('import pack with a path alone and a ref stops', async (t) => {
    const c = await AddRemoveCase.make(t);
    c.write('team-rules/pack.md', 'Use pnpm.\n');
    c.write('context-packs/team/pack.md', '---\npath: team-rules\nref: v1.0.0\n---\n');

    const result = await c.sync();

    exits(result, 1);
    includes(result.stderr, 'context-packs/team/pack.md');
    includes(result.stderr, 'ref');
  });

  test('remove drops the import pack and its generated files', async (t) => {
    const c = await AddRemoveCase.make(t);
    c.publish({ 'testing.md': doc('Writing tests', 'Test behavior.\n') });
    await c.add();

    const result = await c.sync('remove', 'house-rules');

    exits(result, 0);
    assert.equal(c.agents(), block());
    assert.ok(!exists(path.dirname(c.importMd())));
    assert.ok(!exists(c.gen));
  });

  test('remove of a pack not installed stops', async (t) => {
    const c = await AddRemoveCase.make(t);
    await c.sync();

    const result = await c.sync('remove', 'acme');

    exits(result, 1);
    includes(result.stderr, 'acme');
  });

  test('remove of the repos own folder stops and keeps it', async (t) => {
    const c = await AddRemoveCase.make(t);
    const design = c.write('context-packs/project/design.md', doc('Changing the design'));
    await c.sync();

    const result = await c.sync('remove', 'project');

    exits(result, 1);
    includes(result.stderr, 'project');
    assert.ok(exists(design));
  });
});
