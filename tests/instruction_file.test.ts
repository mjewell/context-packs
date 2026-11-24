import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { describe, test } from 'node:test';

import { exits, includes } from './expect.ts';
import { block, EMPTY, exists, masked, names, read, SyncCase } from './sync_case.ts';

/** Whether file is there, even as a link to nothing. */
function lexists(file: string): boolean {
  try {
    fs.lstatSync(file);
    return true;
  } catch {
    return false;
  }
}

/** A repo with neither instruction file yet, and the path CLAUDE.md would have. */
class InstructionCase extends SyncCase {
  readonly claudeMd = path.join(this.repo, 'CLAUDE.md');
}

/**
 * Which file the sync writes: whichever of AGENTS.md and CLAUDE.md holds the block, else AGENTS.md or CLAUDE.md if
 * one exists, else a new AGENTS.md with CLAUDE.md linked to it.
 */
describe('InstructionFileTests', () => {
  test('claude md alone is synced and keeps its own text', async (t) => {
    const c = new InstructionCase(t);
    fs.writeFileSync(c.claudeMd, `# Repo\n\n${EMPTY}\nUse named exports.\n`);

    const result = await c.sync();

    exits(result, 0);
    assert.equal(masked(read(c.claudeMd)), `# Repo\n\n${block()}\nUse named exports.\n`);
    assert.ok(!lexists(c.agentsMd));
  });

  test('pack added to claude md resyncs with nothing changed', async (t) => {
    const c = new InstructionCase(t);
    c.share('Prefer small PRs.\n');
    fs.writeFileSync(c.claudeMd, EMPTY);
    await c.add();

    const result = await c.sync();

    exits(result, 0);
    assert.equal(masked(read(c.claudeMd)), c.rules());
    assert.ok(result.stdout.startsWith('Nothing changed: house-rules @ '), result.stdout);
  });

  test('claude md without a block stops and shows the lines to add', async (t) => {
    const c = new InstructionCase(t);
    fs.writeFileSync(c.claudeMd, 'Old rules.\n');

    const result = await c.sync();

    exits(result, 1);
    includes(result.stderr, `${c.claudeMd} has no context-packs block`);
    includes(result.stderr, EMPTY);
    assert.deepEqual(names(c.repo), ['.git', 'CLAUDE.md']);
    assert.equal(read(c.claudeMd), 'Old rules.\n');
  });

  test('agents md is synced and claude md left alone', async (t) => {
    const c = new InstructionCase(t);
    fs.writeFileSync(c.agentsMd, EMPTY);
    fs.writeFileSync(c.claudeMd, '@AGENTS.md\n');

    const result = await c.sync();

    exits(result, 0);
    assert.equal(c.agents(), block());
    assert.equal(read(c.claudeMd), '@AGENTS.md\n');
  });

  test('existing agents md gets no claude md link', async (t) => {
    const c = new InstructionCase(t);
    fs.writeFileSync(c.agentsMd, EMPTY);

    const result = await c.sync();

    exits(result, 0);
    assert.ok(!lexists(c.claudeMd));
  });

  test('both files without a block stop and leave the choice to the repo', async (t) => {
    const c = new InstructionCase(t);
    fs.writeFileSync(c.agentsMd, 'Codex rules.\n');
    fs.writeFileSync(c.claudeMd, 'Claude rules.\n');

    const result = await c.sync();

    exits(result, 1);
    includes(result.stderr, `Neither ${c.agentsMd} nor ${c.claudeMd} has a context-packs block`);
    includes(result.stderr, EMPTY);
    assert.equal(read(c.agentsMd), 'Codex rules.\n');
    assert.equal(read(c.claudeMd), 'Claude rules.\n');
  });

  test('claude md holding the block stays the one synced once agents md appears', async (t) => {
    const c = new InstructionCase(t);
    fs.writeFileSync(c.claudeMd, EMPTY);
    fs.writeFileSync(c.agentsMd, 'Codex rules.\n');

    const result = await c.sync();

    exits(result, 0);
    assert.equal(masked(read(c.claudeMd)), block());
    assert.equal(read(c.agentsMd), 'Codex rules.\n');
  });

  test('block in both files stops the sync untouched', async (t) => {
    const c = new InstructionCase(t);
    fs.writeFileSync(c.agentsMd, EMPTY);
    fs.writeFileSync(c.claudeMd, EMPTY);

    const result = await c.sync();

    exits(result, 1);
    includes(result.stderr, 'AGENTS.md and');
    includes(result.stderr, 'CLAUDE.md both have a context-packs block');
    assert.equal(read(c.agentsMd), EMPTY);
    assert.equal(read(c.claudeMd), EMPTY);
  });

  test('agents md linked to claude md syncs claude md', async (t) => {
    const c = new InstructionCase(t);
    fs.writeFileSync(c.claudeMd, EMPTY);
    fs.symlinkSync('CLAUDE.md', c.agentsMd);

    const result = await c.sync();

    exits(result, 0);
    assert.equal(masked(read(c.claudeMd)), block());
    assert.equal(fs.readlinkSync(c.agentsMd), 'CLAUDE.md');
  });

  test('claude md linked elsewhere stops the sync untouched', async (t) => {
    const c = new InstructionCase(t);
    const target = path.join(c.source, 'old-rules.md');
    fs.symlinkSync(target, c.claudeMd);

    const result = await c.sync();

    exits(result, 1);
    includes(result.stderr, `${c.claudeMd} is a symlink`);
    assert.ok(!exists(target));
    assert.ok(!lexists(c.agentsMd));
  });
});
