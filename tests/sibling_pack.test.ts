import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { describe, test } from 'node:test';

import { exits, includes } from './expect.ts';
import { command, run } from './scripts.ts';
import { block, doc, exists, HEADER, packed, read, SyncCase } from './sync_case.ts';

/** A pack in a folder beside the synced repo, imported by its path, which syncs from its working tree. */
class SiblingCase extends SyncCase {
  protected override async setUp(): Promise<void> {
    await super.setUp();
    this.publish({ 'pack.md': 'Prefer small PRs.\n', 'testing.md': doc('Writing tests', 'Test behavior.\n') });
  }

  addSibling(...args: string[]) {
    return this.sync('add', 'house-rules', '../house-rules', '--path', 'context', ...args);
  }
}

describe('a pack in a folder beside the repo', () => {
  test('sibling pack syncs its working tree and lists its docs where they are', async (t) => {
    const c = await SiblingCase.make(t);
    fs.writeFileSync(path.join(c.source, 'context', 'pack.md'), 'Prefer tiny PRs.\n');

    const result = await c.addSibling();

    exits(result, 0);
    assert.equal(read(c.importMd()), '---\nfrom: ../house-rules\npath: context\n---\n');
    assert.equal(
      c.agents(),
      block(
        packed(
          'house-rules',
          'Prefer tiny PRs.\n\n## house-rules context\n\n' +
            '| When | Read |\n|---|---|\n' +
            '| Writing tests | `../house-rules/context/testing.md` |\n',
        ),
      ),
    );
    assert.ok(!exists(c.gen));
  });

  test('editing a sibling doc needs no resync', async (t) => {
    const c = await SiblingCase.make(t);
    await c.addSibling();
    const before = read(c.agentsMd);
    fs.writeFileSync(path.join(c.source, 'context', 'testing.md'), doc('Writing tests', 'Test behavior only.\n'));

    const result = await c.sync();

    exits(result, 0);
    assert.equal(read(c.agentsMd), before);
  });

  test('missing sibling folder stops the sync', async (t) => {
    const c = await SiblingCase.make(t);
    await c.addSibling();
    const before = read(c.agentsMd);
    fs.rmSync(c.source, { recursive: true });

    const result = await c.sync();

    exits(result, 1);
    includes(result.stderr, '../house-rules/context');
    assert.equal(read(c.agentsMd), before);
  });

  test('sibling pack takes no ref', async (t) => {
    const c = await SiblingCase.make(t);
    const result = await c.addSibling('--ref', 'v1.0.0');

    exits(result, 1);
    includes(result.stderr, '--ref');
    assert.ok(!exists(c.agentsMd));
  });

  test('sibling pack with a ref in its import pack stops', async (t) => {
    const c = await SiblingCase.make(t);
    await c.addSibling();
    fs.writeFileSync(c.importMd(), '---\nfrom: ../house-rules\npath: context\nref: v1.0.0\n---\n');

    const result = await c.sync();

    exits(result, 1);
    includes(result.stderr, 'context-packs/house-rules/pack.md');
    includes(result.stderr, 'ref');
  });

  test('when on a sibling pack gives it a row', async (t) => {
    const c = await SiblingCase.make(t);
    const result = await c.addSibling('--when', 'Reviewing a PR');

    exits(result, 0);
    includes(c.agents(), '| Reviewing a PR | `context-packs/gen/house-rules/pack.md` |\n');
  });

  test('absolute path is a folder on disk too', async (t) => {
    const c = await SiblingCase.make(t);
    fs.writeFileSync(path.join(c.source, 'context', 'pack.md'), 'Prefer tiny PRs.\n');

    const result = await c.sync('add', 'house-rules', c.source, '--path', 'context');

    exits(result, 0);
    includes(c.agents(), `${HEADER}\n<!-- context-packs:pack house-rules -->\nPrefer tiny PRs.\n`);
    includes(c.agents(), `| Writing tests | \`${c.source}/context/testing.md\` |`);
    assert.ok(!exists(c.gen));
  });

  test('scp style origin is a git url', async (t) => {
    const c = await SiblingCase.make(t);
    const result = await run([...command('src/cli'), 'add', 'acme', 'git@example.invalid:acme/rules.git'], {
      cwd: c.repo,
      timeout: 30_000,
      env: { ...c.env, GIT_SSH_COMMAND: 'false' },
    });

    exits(result, 1);
    includes(result.stderr, 'git ls-remote');
  });

  test('update leaves a sibling pack alone', async (t) => {
    const c = await SiblingCase.make(t);
    await c.addSibling();
    const before = read(c.agentsMd);

    const result = await c.sync('update');

    exits(result, 0);
    assert.equal(read(c.agentsMd), before);
  });

  test('update with a ref of a sibling pack stops', async (t) => {
    const c = await SiblingCase.make(t);
    await c.addSibling();

    const result = await c.sync('update', 'house-rules', '--ref', 'v1.0.0');

    exits(result, 1);
    includes(result.stderr, '--ref');
  });
});
