import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { describe, test } from 'node:test';

import { exits } from './expect.ts';
import { doc, read, SyncCase } from './sync_case.ts';

/** A pack with docs at every level, and a doc of the repo's own, synced. */
class DocsCase extends SyncCase {
  protected override async setUp(): Promise<void> {
    await super.setUp();
    this.publish({
      'pack.md': 'Prefer small PRs.\n',
      'testing.md': doc('Writing tests', 'Test behavior.\n'),
      'frontend/pack.md': doc('Editing `web/**`', 'Keep components small.\n'),
      'frontend/react.md': doc('Writing React components', 'Use function components.\n'),
      'backend/pack.md': doc('always', 'Validate input.\n'),
      'backend/errors.md': doc('Handling errors', 'Raise, never return codes.\n'),
    });
    this.write('context-packs/project/design.md', doc('Changing the design', 'Keep it small.\n'));
    exits(await this.add(), 0);
  }
}

/** The docs command, which lists every file the repo's tables point an agent at, by pack, for the review's prompt. */
describe('docs', () => {
  test('prints every doc the tables point at grouped by pack', async (t) => {
    const c = await DocsCase.make(t);
    const result = await c.sync('docs');

    exits(result, 0);
    assert.equal(
      result.stdout,
      'context-packs/project/design.md\n' +
        '\n' +
        'context-packs/gen/house-rules/testing.md\n' +
        '\n' +
        'context-packs/gen/house-rules/backend/errors.md\n' +
        '\n' +
        'context-packs/gen/house-rules/frontend.md\n' +
        'context-packs/gen/house-rules/frontend/react.md\n',
    );
  });

  test('every path it prints is in agents md or an index', async (t) => {
    const c = await DocsCase.make(t);
    const listed = (await c.sync('docs')).stdout.split('\n').filter(Boolean);
    const tables = read(c.agentsMd) + read(path.join(c.gen, 'house-rules', 'frontend.md'));

    assert.deepEqual(
      listed.filter((file) => !tables.includes(`\`${file}\``)),
      [],
    );
    assert.ok(listed.every((file) => fs.statSync(path.join(c.repo, file)).isFile()));
  });

  test('reads the synced tables without fetching any pack', async (t) => {
    const c = await DocsCase.make(t);
    const expected = (await c.sync('docs')).stdout;
    fs.rmSync(path.join(c.root, 'house-rules.git'), { recursive: true });
    fs.rmSync(path.join(c.root, 'cache'), { recursive: true });

    const result = await c.sync('docs');

    exits(result, 0);
    assert.equal(result.stdout, expected);
  });
});

/** A folder inside a repo, whose tables' paths start from the repo root. */
describe('docs in a folder inside a repo', () => {
  test('lists and reads paths from the repo root', async (t) => {
    const c = await SyncCase.make(t);
    c.write('packages/web/context-packs/frontend/pack.md', doc('Editing `web/**`', 'Keep components small.\n'));
    c.write('packages/web/context-packs/frontend/react.md', doc('Writing React components'));
    const folder = path.join(c.repo, 'packages', 'web');
    assert.equal((await c.sync('--dir', folder)).status, 0);

    const result = await c.sync('--dir', folder, 'docs');

    exits(result, 0);
    assert.equal(
      result.stdout,
      'packages/web/context-packs/gen/frontend.md\n' + 'packages/web/context-packs/frontend/react.md\n',
    );
  });
});
