import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { describe, type TestContext, test } from 'node:test';

import { exits } from './expect.ts';
import { doc, EMPTY, SyncCase } from './sync_case.ts';

/** A repo synced once, with a pack published that it hasn't added yet. */
class ReportCase extends SyncCase {
  first = '';

  static async make(t: TestContext): Promise<ReportCase> {
    const c = new ReportCase(t);
    c.first = c.share('Prefer small PRs.\n');
    await c.sync();
    return c;
  }
}

/** What a sync prints about the changes it made. */
describe('ReportTests', () => {
  test('add names the pack and its ref', async (t) => {
    const c = await ReportCase.make(t);
    const result = await c.add();

    exits(result, 0);
    assert.equal(result.stdout, `house-rules: added @ ${c.first.slice(0, 7)}\n`);
  });

  test('remove names the pack', async (t) => {
    const c = await ReportCase.make(t);
    await c.add();

    const result = await c.sync('remove', 'house-rules');

    exits(result, 0);
    assert.equal(result.stdout, 'house-rules: removed\n');
  });

  test('update shows where the pack moved', async (t) => {
    const c = await ReportCase.make(t);
    await c.add();
    const latest = c.share('Prefer small PRs.\nWrite tests first.\n');

    const result = await c.sync('update');

    exits(result, 0);
    assert.equal(result.stdout, `house-rules: ${c.first.slice(0, 7)} → ${latest.slice(0, 7)}\n`);
  });

  test('update lists every pack it covers', async (t) => {
    const c = await ReportCase.make(t);
    await c.add();
    const [steadyOrigin, steady] = c.remote('steady');
    const steadyRef = c.publish({ 'pack.md': 'Use steady.\n' }, steady);
    await c.sync('add', 'steady', steadyOrigin, '--path', 'context');
    const [taggedOrigin, tagged] = c.remote('tagged');
    c.publish({ 'pack.md': 'Use tagged.\n' }, tagged);
    c.tag('v1.0.0', tagged);
    await c.sync('add', 'tagged', taggedOrigin, '--path', 'context', '--ref', 'v1.0.0');
    const latest = c.share('Prefer small PRs.\nWrite tests first.\n');

    const result = await c.sync('update');

    exits(result, 0);
    assert.equal(
      result.stdout,
      `house-rules: ${c.first.slice(0, 7)} → ${latest.slice(0, 7)}\n` +
        `steady: ${steadyRef.slice(0, 7)} (up to date)\n` +
        'tagged: v1.0.0 (tag)\n',
    );
  });

  test('update to another tag shows the tags in full', async (t) => {
    const c = await ReportCase.make(t);
    c.tag('v1.0.0');
    await c.add('--ref', 'v1.0.0');
    c.share('Prefer small PRs.\nWrite tests first.\n');
    c.tag('v1.1.0');

    const result = await c.sync('update', 'house-rules', '--ref', 'v1.1.0');

    exits(result, 0);
    assert.equal(result.stdout, 'house-rules: v1.0.0 → v1.1.0\n');
  });

  test('update lists no folder on disk', async (t) => {
    const c = await ReportCase.make(t);
    await c.sync('add', 'house-rules', '../house-rules', '--path', 'context');

    const result = await c.sync('update');

    exits(result, 0);
    assert.equal(result.stdout, 'Nothing changed: house-rules\n');
  });

  test('resync with nothing to change says so and names the pins', async (t) => {
    const c = await ReportCase.make(t);
    await c.add();
    c.share('Prefer small PRs.\nWrite tests first.\n');

    const result = await c.sync();

    exits(result, 0);
    assert.equal(result.stdout, `Nothing changed: house-rules @ ${c.first.slice(0, 7)}\n`);
  });

  test('resync without import packs says nothing changed', async (t) => {
    const c = await ReportCase.make(t);
    const result = await c.sync();

    exits(result, 0);
    assert.equal(result.stdout, 'Nothing changed\n');
  });

  test('add of a folder on disk names no ref', async (t) => {
    const c = await ReportCase.make(t);
    c.write('team-rules/pack.md', 'Use pnpm.\n');

    const result = await c.sync('add', 'team', 'team-rules');

    exits(result, 0);
    assert.equal(result.stdout, 'team: added\n');
  });

  test('resync after the repos own docs change says the block changed', async (t) => {
    const c = await ReportCase.make(t);
    c.write('context-packs/design.md', doc('Changing the design'));

    const result = await c.sync();

    exits(result, 0);
    assert.equal(result.stdout, 'Updated the context-packs block\n');
  });

  test('filling a pasted block says so', async (t) => {
    const c = await ReportCase.make(t);
    fs.writeFileSync(c.agentsMd, `# Repo\n\n${EMPTY}`);

    const result = await c.sync();

    exits(result, 0);
    assert.equal(result.stdout, 'Updated the context-packs block\n');
  });

  test('first sync says it created agents md and linked claude md', async (t) => {
    const c = await ReportCase.make(t);
    fs.unlinkSync(c.agentsMd);
    fs.unlinkSync(path.join(c.repo, 'CLAUDE.md'));

    const result = await c.sync();

    exits(result, 0);
    assert.equal(result.stdout, 'Created AGENTS.md\nLinked CLAUDE.md to AGENTS.md\n');
  });

  test('resync after claude md is deleted leaves it deleted', async (t) => {
    const c = await ReportCase.make(t);
    fs.unlinkSync(path.join(c.repo, 'CLAUDE.md'));

    const result = await c.sync();

    exits(result, 0);
    assert.equal(result.stdout, 'Nothing changed\n');
    assert.ok(!fs.lstatSync(path.join(c.repo, 'CLAUDE.md'), { throwIfNoEntry: false })?.isSymbolicLink());
  });
});
