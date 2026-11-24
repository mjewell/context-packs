import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { describe, test } from 'node:test';

import { excludes, exits, includes } from './expect.ts';
import { block, CLAUSE, EMPTY, exists, names, OUTSIDE_CLAUSE, read, SyncCase } from './sync_case.ts';

describe('sync', () => {
  test('fresh repo gets agents md holding only the header', async (t) => {
    const c = await SyncCase.make(t);
    const result = await c.sync();

    exits(result, 0);
    assert.equal(c.agents(), block());
  });

  test('fresh repo gets claude md linked to agents md', async (t) => {
    const c = await SyncCase.make(t);
    const result = await c.sync();

    exits(result, 0);
    assert.equal(fs.readlinkSync(path.join(c.repo, 'CLAUDE.md')), 'AGENTS.md');
  });

  test('block edited in the repo stops the sync untouched', async (t) => {
    const c = await SyncCase.make(t);
    c.share('Prefer small PRs.\n');
    await c.add();
    const edited = read(c.agentsMd).replace('small PRs', 'tiny PRs');
    fs.writeFileSync(c.agentsMd, edited);
    c.share('Prefer small PRs.\nWrite tests first.\n');

    const result = await c.sync('update');

    exits(result, 1);
    includes(result.stderr, 'was edited');
    assert.equal(read(c.agentsMd), edited);
  });

  test('header edited in the repo stops the sync untouched', async (t) => {
    const c = await SyncCase.make(t);
    await c.sync();
    const edited = read(c.agentsMd).replace('never here', 'rarely here');
    fs.writeFileSync(c.agentsMd, edited);

    const result = await c.sync();

    exits(result, 1);
    includes(result.stderr, 'was edited');
    assert.equal(read(c.agentsMd), edited);
  });

  test('agents md without a block stops and shows the lines to add', async (t) => {
    const c = await SyncCase.make(t);
    fs.writeFileSync(c.agentsMd, '# Repo\n');

    const result = await c.sync();

    exits(result, 1);
    includes(result.stderr, EMPTY);
    assert.equal(read(c.agentsMd), '# Repo\n');
  });

  test('dir syncs that folder instead of the current one', async (t) => {
    const c = await SyncCase.make(t);
    const elsewhere = path.join(c.root, 'elsewhere');
    fs.mkdirSync(elsewhere);

    const result = await c.syncIn(elsewhere, '--dir', c.repo);

    exits(result, 0);
    assert.equal(c.agents(), block());
    assert.deepEqual(names(elsewhere), []);
  });

  test('missing dir stops the sync', async (t) => {
    const c = await SyncCase.make(t);
    const missing = path.join(c.repo, 'not-a-repo');

    const result = await c.sync('--dir', missing);

    exits(result, 1);
    includes(result.stderr, `context-packs: ${missing} is not a folder`);
  });

  test('usage errors name the tool', async (t) => {
    const c = await SyncCase.make(t);
    const result = await c.sync('publish');

    exits(result, 2);
    assert.ok(result.stderr.startsWith('usage: context-packs '), result.stderr);
  });

  test('agents md that is a link stops the sync untouched', async (t) => {
    const c = await SyncCase.make(t);
    const target = path.join(c.source, 'old-rules.md');
    fs.symlinkSync(target, c.agentsMd);

    const result = await c.sync();

    exits(result, 1);
    includes(result.stderr, 'symlink');
    assert.ok(!exists(target));
  });

  test('folder that is not a repo gets agents md and claude md', async (t) => {
    const c = await SyncCase.make(t);
    fs.rmSync(path.join(c.repo, '.git'), { recursive: true });

    const result = await c.sync();

    exits(result, 0);
    assert.equal(c.agents(), block().replace(CLAUSE, OUTSIDE_CLAUSE));
    assert.equal(fs.readlinkSync(path.join(c.repo, 'CLAUDE.md')), 'AGENTS.md');
  });

  test('block repeated stops the sync untouched', async (t) => {
    const c = await SyncCase.make(t);
    await c.sync();
    const doubled = `${read(c.agentsMd)}\n${EMPTY}`;
    fs.writeFileSync(c.agentsMd, doubled);

    const result = await c.sync();

    exits(result, 1);
    includes(result.stderr, 'more than one context-packs block');
    assert.equal(read(c.agentsMd), doubled);
  });

  test('blocks from an older version stop and show the lines to use', async (t) => {
    const c = await SyncCase.make(t);
    const old =
      '# Repo\n\n<!-- context-packs:start header -->\n<!-- context-packs:end sha256:e3b0c44298fc -->\n\n' +
      '<!-- context-packs:start core path=docs/agents/core -->\n<!-- context-packs:end sha256:e3b0c44298fc -->\n';
    fs.writeFileSync(c.agentsMd, old);

    const result = await c.sync();

    exits(result, 1);
    includes(result.stderr, 'older version');
    includes(result.stderr, EMPTY);
    includes(result.stderr, 'Move each import pack in docs/agents/');
    excludes(result.stderr, 'add the packs again');
    assert.equal(read(c.agentsMd), old);
  });

  test('shared rules without a final newline still resync', async (t) => {
    const c = await SyncCase.make(t);
    c.share('Prefer small PRs.');
    await c.add();

    const result = await c.sync();

    exits(result, 0);
    assert.equal(c.agents(), c.rules());
  });

  test('agents md with crlf line endings stops the sync untouched', async (t) => {
    const c = await SyncCase.make(t);
    const crlf = `# Repo\n\n${EMPTY}`.replaceAll('\n', '\r\n');
    fs.writeFileSync(c.agentsMd, crlf);

    const result = await c.sync();

    exits(result, 1);
    includes(result.stderr, 'CRLF');
    assert.equal(read(c.agentsMd), crlf);
  });

  test('pasted empty block gets filled', async (t) => {
    const c = await SyncCase.make(t);
    fs.writeFileSync(c.agentsMd, `# Repo\n\n${EMPTY}\nUse pnpm.\n`);

    const result = await c.sync();

    exits(result, 0);
    assert.equal(c.agents(), `# Repo\n\n${block()}\nUse pnpm.\n`);
  });

  test('stray file in the generated folder stops the sync', async (t) => {
    const c = await SyncCase.make(t);
    await c.sync();
    const stray = c.write('context-packs/gen/acme/index.md', 'Use acme.\n');

    const result = await c.sync();

    exits(result, 1);
    includes(result.stderr, 'context-packs/gen');
    assert.ok(exists(stray));
  });
});
