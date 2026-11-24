import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { describe, test } from 'node:test';

import { exits, includes } from './expect.ts';
import { block, doc, exists, names, packed, read, SyncCase } from './sync_case.ts';

/** Every file under folder, by its path from there, sorted. */
function files(folder: string): string[] {
  return (fs.readdirSync(folder, { recursive: true, withFileTypes: true }) as fs.Dirent[])
    .filter((entry) => entry.isFile())
    .map((entry) => path.relative(folder, path.join(entry.parentPath, entry.name)))
    .sort();
}

/** A case with the folder its pack is synced into. */
class SyncedCase extends SyncCase {
  get synced(): string {
    return path.join(this.gen, 'house-rules');
  }
}

class FolderCase extends SyncedCase {
  protected override async setUp(): Promise<void> {
    await super.setUp();
    this.publish({
      'pack.md': 'Prefer small PRs.\n',
      'typescript/react.md': doc('Writing React components', 'Use function components.\n'),
      'typescript/types.md': doc('Declaring types', 'Prefer unions.\n'),
      'typescript/example.tsx': 'export const x = 1;\n',
    });
  }
}

/** A folder without a pack.md, which only groups files: its docs join the nearest pack's table. */
describe('a folder without a pack.md', () => {
  test('folder docs join the packs table', async (t) => {
    const c = await FolderCase.make(t);
    const result = await c.add();

    exits(result, 0);
    assert.equal(
      c.agents(),
      block(
        packed(
          'house-rules',
          'Prefer small PRs.\n\n## house-rules context\n\n' +
            '| When | Read |\n|---|---|\n' +
            '| Writing React components | `context-packs/gen/house-rules/typescript/react.md` |\n' +
            '| Declaring types | `context-packs/gen/house-rules/typescript/types.md` |\n',
        ),
      ),
    );
  });

  test('every file in the folder is copied', async (t) => {
    const c = await FolderCase.make(t);
    const result = await c.add();

    exits(result, 0);
    assert.deepEqual(names(path.join(c.synced, 'typescript')), ['example.tsx', 'react.md', 'types.md']);
    assert.equal(read(path.join(c.synced, 'typescript', 'example.tsx')), 'export const x = 1;\n');
  });
});

class NestedCase extends SyncedCase {
  protected override async setUp(): Promise<void> {
    await super.setUp();
    this.publish({
      'pack.md': 'Prefer small PRs.\n',
      'testing.md': doc('Writing tests', 'Test behavior.\n'),
      'frontend/pack.md': doc('Editing `web/**`', 'Keep components small.\n'),
      'frontend/react.md': doc('Writing React components', 'Use function components.\n'),
      'frontend/css/layout.md': doc('Laying out pages', 'Use grid.\n'),
    });
  }
}

/** A folder with a pack.md inside the installed pack, which gets a row pointing at a generated index. */
describe('a nested pack', () => {
  test('nested pack gets a row in its parents table', async (t) => {
    const c = await NestedCase.make(t);
    const result = await c.add();

    exits(result, 0);
    assert.equal(
      c.agents(),
      block(
        packed(
          'house-rules',
          'Prefer small PRs.\n\n## house-rules context\n\n' +
            '| When | Read |\n|---|---|\n' +
            '| Editing `web/**` | `context-packs/gen/house-rules/frontend.md` |\n' +
            '| Writing tests | `context-packs/gen/house-rules/testing.md` |\n',
        ),
      ),
    );
  });

  test('nested pack whose when is always is inlined after its parent between markers', async (t) => {
    const c = await NestedCase.make(t);
    c.publish({ 'frontend/pack.md': doc('always', 'Keep components small.\n') });

    const result = await c.add();

    exits(result, 0);
    includes(
      c.agents(),
      '| Writing tests | `context-packs/gen/house-rules/testing.md` |\n\n' +
        '<!-- context-packs:pack house-rules/frontend -->\nKeep components small.\n\n' +
        '## house-rules/frontend context\n\n| When | Read |\n|---|---|\n' +
        '| Laying out pages | `context-packs/gen/house-rules/frontend/css/layout.md` |\n' +
        '| Writing React components | `context-packs/gen/house-rules/frontend/react.md` |\n' +
        '<!-- context-packs:pack-end house-rules/frontend -->\n' +
        '<!-- context-packs:pack-end house-rules -->\n',
    );
    assert.ok(!exists(path.join(c.synced, 'frontend.md')));
    assert.ok(exists(path.join(c.synced, 'frontend', 'react.md')));
  });

  test('nested packs index holds its rules and table without front matter', async (t) => {
    const c = await NestedCase.make(t);
    const result = await c.add();

    exits(result, 0);
    assert.equal(
      read(path.join(c.synced, 'frontend.md')),
      'Keep components small.\n\n## house-rules/frontend context\n\n| When | Read |\n|---|---|\n' +
        '| Laying out pages | `context-packs/gen/house-rules/frontend/css/layout.md` |\n' +
        '| Writing React components | `context-packs/gen/house-rules/frontend/react.md` |\n',
    );
  });

  test('nested packs files are copied without its pack md', async (t) => {
    const c = await NestedCase.make(t);
    const result = await c.add();

    exits(result, 0);
    assert.deepEqual(files(c.synced), ['frontend.md', 'frontend/css/layout.md', 'frontend/react.md', 'testing.md']);
  });

  test('generated index edited in the repo stops the sync', async (t) => {
    const c = await NestedCase.make(t);
    await c.add();
    const index = path.join(c.synced, 'frontend.md');
    fs.writeFileSync(index, 'Edited here.\n');

    const result = await c.sync();

    exits(result, 1);
    includes(result.stderr, 'context-packs/gen');
    assert.equal(read(index), 'Edited here.\n');
  });

  test('nested pack without a when line stops the sync', async (t) => {
    const c = await NestedCase.make(t);
    c.publish({ 'backend/pack.md': 'Use Rails.\n' });

    const result = await c.add();

    exits(result, 1);
    includes(result.stderr, 'context/backend/pack.md');
    assert.ok(!exists(c.agentsMd));
  });

  test('doc without a when line stops the sync', async (t) => {
    const c = await NestedCase.make(t);
    c.publish({ 'frontend/css/grid.md': 'Use grid.\n' });

    const result = await c.add();

    exits(result, 1);
    includes(result.stderr, 'context/frontend/css/grid.md');
    assert.ok(!exists(c.agentsMd));
  });

  test('doc whose when is always stops the sync', async (t) => {
    const c = await NestedCase.make(t);
    c.publish({ 'testing.md': doc('always', 'Test behavior.\n') });

    const result = await c.add();

    exits(result, 1);
    includes(result.stderr, 'context/testing.md');
    includes(result.stderr, 'pack.md');
    assert.ok(!exists(c.agentsMd));
  });

  test('tier on a doc stops the sync', async (t) => {
    const c = await NestedCase.make(t);
    c.publish({ 'testing.md': doc('Writing tests', '', { tier: 'required' }) });

    const result = await c.add();

    exits(result, 1);
    includes(result.stderr, 'context/testing.md');
    includes(result.stderr, 'tier');
  });

  test('stray file in the synced folder stops the sync', async (t) => {
    const c = await NestedCase.make(t);
    await c.add();
    fs.writeFileSync(path.join(c.synced, '.DS_Store'), '');

    const result = await c.sync();

    exits(result, 1);
    includes(result.stderr, 'a file in context-packs/gen was edited');
    assert.ok(exists(path.join(c.synced, '.DS_Store')));
  });

  test('nested pack beside a doc of the same name stops the sync', async (t) => {
    const c = await NestedCase.make(t);
    c.publish({ 'frontend.md': doc('Editing the frontend') });

    const result = await c.add();

    exits(result, 1);
    includes(result.stderr, 'frontend');
    assert.ok(!exists(c.agentsMd));
  });
});

/** A pack and a folder inside it installed from the same origin. */
class OverlapCase extends SyncCase {
  protected override async setUp(): Promise<void> {
    await super.setUp();
    this.publish({
      'pack.md': 'Prefer small PRs.\n',
      'typescript/pack.md': doc('Editing `**/*.ts`', 'Prefer unions.\n'),
    });
  }

  addTypescript(origin = this.origin) {
    return this.sync('add', 'typescript', origin, '--path', 'context/typescript');
  }
}

describe('overlapping packs', () => {
  test('adding a folder inside an installed pack stops untouched', async (t) => {
    const c = await OverlapCase.make(t);
    await c.add();
    const before = read(c.agentsMd);

    const result = await c.addTypescript();

    exits(result, 1);
    includes(result.stderr, 'overlap');
    includes(result.stderr, 'house-rules');
    includes(result.stderr, 'typescript');
    assert.equal(read(c.agentsMd), before);
    assert.ok(!exists(path.dirname(c.importMd('typescript'))));
  });

  test('adding a pack around an installed one stops untouched', async (t) => {
    const c = await OverlapCase.make(t);
    await c.addTypescript();
    const before = read(c.agentsMd);

    const result = await c.add();

    exits(result, 1);
    includes(result.stderr, 'overlap');
    assert.equal(read(c.agentsMd), before);
  });

  test('same folder from another origin doesnt overlap', async (t) => {
    const c = await OverlapCase.make(t);
    const [otherOrigin, other] = c.remote('other-rules');
    c.publish({ 'typescript/pack.md': doc('Editing `**/*.ts`', 'Use strict mode.\n') }, other);
    await c.add();

    const result = await c.addTypescript(otherOrigin);

    exits(result, 0);
  });
});

/** A folder with a pack.md installed on its own, which renders the way it would inside its parent. */
class InstallPointCase extends SyncCase {
  get synced(): string {
    return path.join(this.gen, 'typescript');
  }

  protected override async setUp(): Promise<void> {
    await super.setUp();
    this.publish({
      'pack.md': 'Prefer small PRs.\n',
      'typescript/pack.md': doc('Editing `**/*.ts`', 'Prefer unions.\n'),
      'typescript/types.md': doc('Declaring types'),
    });
  }

  addFolder(name: string) {
    return this.sync('add', name, this.origin, '--path', `context/${name}`);
  }
}

describe('a nested pack installed on its own', () => {
  test('pack with a when line gets a row in the context table', async (t) => {
    const c = await InstallPointCase.make(t);
    const result = await c.addFolder('typescript');

    exits(result, 0);
    assert.equal(
      c.agents(),
      block(
        '## Context\n\n| When | Read |\n|---|---|\n' +
          '| Editing `**/*.ts` | `context-packs/gen/typescript/pack.md` |\n',
      ),
    );
  });

  test('pack with a when line gets an index of its rules and table', async (t) => {
    const c = await InstallPointCase.make(t);
    const result = await c.addFolder('typescript');

    exits(result, 0);
    assert.equal(
      read(path.join(c.synced, 'pack.md')),
      'Prefer unions.\n\n## typescript context\n\n| When | Read |\n|---|---|\n' +
        '| Declaring types | `context-packs/gen/typescript/types.md` |\n',
    );
  });

  test('nested pack named pack beside a root index stops the sync', async (t) => {
    const c = await InstallPointCase.make(t);
    c.publish({ 'typescript/pack/pack.md': doc('Packaging') });

    const result = await c.addFolder('typescript');

    exits(result, 1);
    includes(result.stderr, 'context/typescript/pack');
    assert.ok(!exists(c.agentsMd));
  });
});

/**
 * A nested pack in the repo's own context-packs/: its docs stay where they are, and only its index is generated.
 */
class LocalNestedCase extends SyncCase {
  get index(): string {
    return path.join(this.gen, 'project', 'deploy.md');
  }

  protected override async setUp(): Promise<void> {
    await super.setUp();
    this.write('context-packs/project/design.md', doc('Changing the design', 'Keep it small.\n'));
    this.write('context-packs/project/deploy/pack.md', doc('Deploying', 'Ship on green.\n'));
    this.write('context-packs/project/deploy/rollback.md', doc('Rolling back', 'Revert first.\n'));
  }
}

describe("a nested pack in the repo's own docs", () => {
  test('nested packs index is generated and its docs stay where they are', async (t) => {
    const c = await LocalNestedCase.make(t);
    const result = await c.sync();

    exits(result, 0);
    assert.equal(
      c.agents(),
      block(
        '## Context\n\n| When | Read |\n|---|---|\n' +
          '| Deploying | `context-packs/gen/project/deploy.md` |\n' +
          '| Changing the design | `context-packs/project/design.md` |\n',
      ),
    );
    assert.equal(
      read(c.index),
      'Ship on green.\n\n## project/deploy context\n\n| When | Read |\n|---|---|\n' +
        '| Rolling back | `context-packs/project/deploy/rollback.md` |\n',
    );
    assert.deepEqual(names(path.dirname(c.index)), ['deploy.md']);
  });

  test('generated index edited in the repo stops the sync', async (t) => {
    const c = await LocalNestedCase.make(t);
    await c.sync();
    fs.writeFileSync(c.index, 'Edited here.\n');

    const result = await c.sync();

    exits(result, 1);
    includes(result.stderr, 'context-packs/gen');
    assert.equal(read(c.index), 'Edited here.\n');
  });

  test('editing a nested packs rules regenerates its index on resync', async (t) => {
    const c = await LocalNestedCase.make(t);
    await c.sync();
    c.write('context-packs/project/deploy/pack.md', doc('Deploying', 'Ship on green, never on Friday.\n'));

    const result = await c.sync();

    exits(result, 0);
    assert.ok(read(c.index).startsWith('Ship on green, never on Friday.\n'));
  });
});
