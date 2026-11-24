import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { describe, type TestContext, test } from 'node:test';

import { excludes, exits, includes } from './expect.ts';
import { block, doc, exists, git, HEADER, packed, read, SyncCase } from './sync_case.ts';

/** The house-rules pack imported into a folder of the repo's own docs, context-packs/project/. */
class ImportPackCase extends SyncCase {
  ref: string;
  readonly id = 'project/house-rules';
  readonly generated = path.join(this.gen, 'project', 'house-rules');

  constructor(t: TestContext) {
    super(t);
    this.ref = this.publish({
      'pack.md': 'Prefer small PRs.\n',
      'testing.md': doc('Writing tests', 'Test behavior.\n'),
    });
    this.write('context-packs/project/design.md', doc('Changing the design', 'Keep it small.\n'));
  }

  importRules(...args: string[]) {
    return this.addAs('project/house-rules', ...args);
  }
}

describe('ImportTests', () => {
  test('add at a nested id writes an import pack pinned to the latest commit', async (t) => {
    const c = new ImportPackCase(t);
    const result = await c.importRules('--when', 'Reviewing a PR');

    exits(result, 0);
    assert.equal(read(c.importMd(c.id)), c.front(c.ref, { when: 'Reviewing a PR' }));
    includes(result.stdout, `project/house-rules: added @ ${c.ref.slice(0, 7)}\n`);
  });

  test('import pack with a when gets a row in its parents table', async (t) => {
    const c = new ImportPackCase(t);
    const result = await c.importRules('--when', 'Reviewing a PR');

    exits(result, 0);
    assert.equal(
      c.agents(),
      block(
        '## Context\n\n| When | Read |\n|---|---|\n' +
          '| Changing the design | `context-packs/project/design.md` |\n' +
          '| Reviewing a PR | `context-packs/gen/project/house-rules/pack.md` |\n',
      ),
    );
    assert.equal(
      read(path.join(c.generated, 'pack.md')),
      'Prefer small PRs.\n\n## project/house-rules context\n\n| When | Read |\n|---|---|\n' +
        '| Writing tests | `context-packs/gen/project/house-rules/testing.md` |\n',
    );
    assert.equal(read(path.join(c.generated, 'testing.md')), doc('Writing tests', 'Test behavior.\n'));
  });

  test('import pack without a when is inlined after its parent', async (t) => {
    const c = new ImportPackCase(t);
    const result = await c.importRules();

    exits(result, 0);
    assert.equal(
      c.agents(),
      block(
        '## Context\n\n| When | Read |\n|---|---|\n' +
          '| Changing the design | `context-packs/project/design.md` |\n\n' +
          packed(
            'project/house-rules',
            'Prefer small PRs.\n\n## project/house-rules context\n\n' +
              '| When | Read |\n|---|---|\n' +
              '| Writing tests | `context-packs/gen/project/house-rules/testing.md` |\n',
          ),
      ),
    );
    assert.ok(!exists(path.join(c.generated, 'pack.md')));
  });

  test('import pack without a when follows its authors', async (t) => {
    const c = new ImportPackCase(t);
    c.ref = c.share(doc('Working on anything', 'Prefer small PRs.\n'));

    const result = await c.importRules();

    exits(result, 0);
    includes(c.agents(), '| Working on anything | `context-packs/gen/project/house-rules/pack.md` |\n');
  });

  test('import packs when replaces its authors', async (t) => {
    const c = new ImportPackCase(t);
    c.ref = c.share(doc('Working on anything', 'Prefer small PRs.\n'));

    const result = await c.importRules('--when', 'Reviewing a PR');

    exits(result, 0);
    includes(c.agents(), '| Reviewing a PR | `context-packs/gen/project/house-rules/pack.md` |\n');
    excludes(c.agents(), 'Working on anything');
  });

  test('when always inlines the pack even with its authors when', async (t) => {
    const c = new ImportPackCase(t);
    c.ref = c.share(doc('Working on anything', 'Prefer small PRs.\n'));

    const result = await c.importRules('--when', 'always');

    exits(result, 0);
    includes(
      c.agents(),
      '\n\n<!-- context-packs:pack project/house-rules -->\nPrefer small PRs.\n\n' + '## project/house-rules context',
    );
    excludes(c.agents(), 'Working on anything');
  });

  test('rules written in the import pack come before the imported ones', async (t) => {
    const c = new ImportPackCase(t);
    await c.importRules();
    fs.writeFileSync(c.importMd(c.id), `${c.front(c.ref)}Small means under 200 lines.\n`);

    const result = await c.sync();

    exits(result, 0);
    includes(
      c.agents(),
      '<!-- context-packs:pack project/house-rules -->\nSmall means under 200 lines.\n\n' + 'Prefer small PRs.\n',
    );
  });

  test('packs nested in the imported pack render as written', async (t) => {
    const c = new ImportPackCase(t);
    c.ref = c.publish({ 'frontend/pack.md': doc('Editing `web/**`', 'Keep components small.\n') });

    const result = await c.importRules('--when', 'Reviewing a PR');

    exits(result, 0);
    includes(
      read(path.join(c.generated, 'pack.md')),
      '| Editing `web/**` | `context-packs/gen/project/house-rules/frontend.md` |\n',
    );
    assert.equal(read(path.join(c.generated, 'frontend.md')), 'Keep components small.\n');
  });

  test('import pack in a nested pack renders into its index', async (t) => {
    const c = new ImportPackCase(t);
    c.write('context-packs/project/review/pack.md', doc('Reviewing code', 'Read the tests first.\n'));

    const result = await c.addAs('project/review/house-rules');

    exits(result, 0);
    assert.equal(
      read(path.join(c.gen, 'project', 'review.md')),
      'Read the tests first.\n\n' +
        packed(
          'project/review/house-rules',
          'Prefer small PRs.\n\n## project/review/house-rules context\n\n' +
            '| When | Read |\n|---|---|\n' +
            '| Writing tests | `context-packs/gen/project/review/house-rules/testing.md` |\n',
        ),
    );
  });

  test('import pack moved to another folder renders there on resync', async (t) => {
    const c = new ImportPackCase(t);
    await c.importRules();
    c.write('context-packs/project/review/pack.md', doc('Reviewing code', 'Read the tests first.\n'));
    fs.renameSync(path.dirname(c.importMd(c.id)), path.join(c.packs, 'project', 'review', 'house-rules'));

    const result = await c.sync();

    exits(result, 0);
    excludes(c.agents(), 'Prefer small PRs.');
    includes(
      read(path.join(c.gen, 'project', 'review.md')),
      'Read the tests first.\n\n<!-- context-packs:pack project/review/house-rules -->\n' + 'Prefer small PRs.\n',
    );
    assert.ok(!exists(c.generated));
  });

  test('update moves the import packs pin and keeps the rest of it', async (t) => {
    const c = new ImportPackCase(t);
    await c.importRules('--when', 'Reviewing a PR');
    fs.writeFileSync(c.importMd(c.id), `${read(c.importMd(c.id))}Small means under 200 lines.\n`);
    const latest = c.share('Prefer small PRs.\nWrite tests first.\n');

    const result = await c.sync('update');

    exits(result, 0);
    assert.equal(
      read(c.importMd(c.id)),
      `${c.front(latest, { when: 'Reviewing a PR' })}Small means under 200 lines.\n`,
    );
    includes(read(path.join(c.generated, 'pack.md')), 'Write tests first.');
    assert.equal(result.stdout, `project/house-rules: ${c.ref.slice(0, 7)} → ${latest.slice(0, 7)}\n`);
  });

  test('update by id moves only that import pack', async (t) => {
    const c = new ImportPackCase(t);
    await c.importRules();
    const latest = c.share('Prefer small PRs.\nWrite tests first.\n');

    const result = await c.sync('update', 'project/house-rules');

    exits(result, 0);
    assert.equal(read(c.importMd(c.id)), c.front(latest));
  });

  test('resync keeps the import pack at its pin', async (t) => {
    const c = new ImportPackCase(t);
    await c.importRules();
    c.share('Prefer small PRs.\nWrite tests first.\n');

    const result = await c.sync();

    exits(result, 0);
    excludes(c.agents(), 'Write tests first.');
  });

  test('resync with nothing to change names the import packs pin', async (t) => {
    const c = new ImportPackCase(t);
    await c.importRules();

    const result = await c.sync();

    exits(result, 0);
    assert.equal(result.stdout, `Nothing changed: project/house-rules @ ${c.ref.slice(0, 7)}\n`);
  });

  test('remove deletes the import pack and its generated files', async (t) => {
    const c = new ImportPackCase(t);
    await c.importRules();

    const result = await c.sync('remove', 'project/house-rules');

    exits(result, 0);
    assert.ok(!exists(path.dirname(c.importMd(c.id))));
    assert.ok(!exists(c.generated));
    assert.ok(exists(path.join(c.packs, 'project', 'design.md')));
    excludes(c.agents(), 'Prefer small PRs.');
    assert.equal(result.stdout, 'project/house-rules: removed\n');
  });

  test('deleting the import pack by hand clears its files on resync', async (t) => {
    const c = new ImportPackCase(t);
    await c.importRules();
    fs.rmSync(path.dirname(c.importMd(c.id)), { recursive: true });

    const result = await c.sync();

    exits(result, 0);
    assert.ok(!exists(c.gen));
  });

  test('list shows import packs by id', async (t) => {
    const c = new ImportPackCase(t);
    await c.importRules();

    const result = await c.sync('list');

    exits(result, 0);
    assert.equal(result.stdout, `project/house-rules  ${c.origin}  context @ ${c.ref}\n`);
  });

  test('editing an imported doc stops the next sync', async (t) => {
    const c = new ImportPackCase(t);
    await c.importRules('--when', 'Reviewing a PR');
    fs.writeFileSync(path.join(c.generated, 'testing.md'), 'Edited here.\n');

    const result = await c.sync();

    exits(result, 1);
    includes(result.stderr, 'context-packs/gen');
    assert.equal(read(path.join(c.generated, 'testing.md')), 'Edited here.\n');
  });
});

/** What stops a sync with import packs. */
describe('ImportRuleTests', () => {
  test('two import packs of one folder both render', async (t) => {
    const c = new ImportPackCase(t);
    await c.importRules();

    const result = await c.addAs('shared');

    exits(result, 0);
    includes(c.agents(), '## project/house-rules context');
    includes(c.agents(), '## shared context');
  });

  test('import pack of a folder inside another import packs stops', async (t) => {
    const c = new ImportPackCase(t);
    c.ref = c.publish({ 'review/pack.md': doc('Reviewing code', 'Read the tests first.\n') });
    assert.equal((await c.importRules()).status, 0);

    const result = await c.sync('add', 'review', c.origin, '--path', 'context/review');

    exits(result, 1);
    includes(result.stderr, 'overlap');
    assert.ok(!exists(c.importMd('review')));
  });

  test('import pack holding another file stops', async (t) => {
    const c = new ImportPackCase(t);
    await c.importRules();
    c.write(`context-packs/${c.id}/notes.md`, doc('Taking notes'));

    const result = await c.sync();

    exits(result, 1);
    includes(result.stderr, 'context-packs/project/house-rules');
    includes(result.stderr, 'notes.md');
  });

  test('add inside an import packs folder stops untouched', async (t) => {
    const c = new ImportPackCase(t);
    await c.importRules();
    const before = read(c.agentsMd);
    const [otherOrigin, other] = c.remote('other-rules');
    c.publish({ 'pack.md': 'Use tabs.\n' }, other);

    const result = await c.sync('add', `${c.id}/other`, otherOrigin, '--path', 'context');

    exits(result, 1);
    includes(result.stderr, 'context-packs/project/house-rules');
    assert.ok(!exists(path.dirname(c.importMd(`${c.id}/other`))));
    assert.equal(read(c.agentsMd), before);
  });

  test('fetched pack holding an import pack from git stops', async (t) => {
    const c = new ImportPackCase(t);
    const [otherOrigin, other] = c.remote('other-rules');
    c.publish({ 'pack.md': 'Use tabs.\n' }, other);
    c.publish({
      'other/pack.md': `---\nfrom: ${otherOrigin}\npath: context\nref: ${git(other, 'rev-parse', 'HEAD')}\n---\n`,
    });

    const result = await c.importRules();

    exits(result, 1);
    includes(result.stderr, 'context/other/pack.md');
    includes(result.stderr, 'from git');
    assert.ok(!exists(path.dirname(c.importMd(c.id))));
  });

  test('import pack of a folder holding context packs stops untouched', async (t) => {
    const c = new ImportPackCase(t);
    const result = await c.sync('add', 'self', '.');

    exits(result, 1);
    includes(result.stderr, 'overlap');
    assert.ok(!exists(path.dirname(c.importMd('self'))));
  });

  test('import pack of a folder inside context packs stops untouched', async (t) => {
    const c = new ImportPackCase(t);
    const result = await c.sync('add', 'loop', 'context-packs/project');

    exits(result, 1);
    includes(result.stderr, 'overlap');
    assert.ok(!exists(path.dirname(c.importMd('loop'))));
  });
});

/**
 * A pack whose common/ folder is an import pack with a path and no from. The path is a folder of that pack's repo, so a
 * pack can point at another folder of its own repo, and works the same wherever it's installed.
 */
function pathImportCase(t: TestContext): SyncCase {
  const c = new SyncCase(t);
  c.publish({ 'pack.md': 'Prefer small PRs.\n', 'common/pack.md': '---\npath: common\n---\n' });
  c.publish({ 'pack.md': 'Use tabs.\n', 'style.md': doc('Styling code', 'Indent once.\n') }, c.source, 'common');
  return c;
}

describe('PathImportTests', () => {
  test('path import in a pack from git reads its repo at the packs ref', async (t) => {
    const c = pathImportCase(t);
    const result = await c.add();

    exits(result, 0);
    assert.equal(
      c.agents(),
      block(
        packed(
          'house-rules',
          'Prefer small PRs.\n\n' +
            packed(
              'house-rules/common',
              'Use tabs.\n\n## house-rules/common context\n\n' +
                '| When | Read |\n|---|---|\n' +
                '| Styling code | `context-packs/gen/house-rules/common/style.md` |\n',
            ),
        ),
      ),
    );
    assert.equal(read(path.join(c.gen, 'house-rules', 'common', 'style.md')), doc('Styling code', 'Indent once.\n'));
  });

  test('path import in a pack from git moves only with its pin', async (t) => {
    const c = pathImportCase(t);
    await c.add();
    c.publish({ 'pack.md': 'Use spaces.\n' }, c.source, 'common');

    const resynced = await c.sync();
    exits(resynced, 0);
    includes(c.agents(), 'Use tabs.\n');

    const updated = await c.sync('update');
    exits(updated, 0);
    includes(c.agents(), 'Use spaces.\n');
  });

  test('path import reaching outside its repo stops', async (t) => {
    const c = pathImportCase(t);
    c.publish({ 'common/pack.md': '---\npath: ../elsewhere\n---\n' });

    const result = await c.add();

    exits(result, 1);
    includes(result.stderr, 'context/common/pack.md');
    includes(result.stderr, 'outside');
  });

  test('import pack from a folder on disk in a pack from git stops', async (t) => {
    const c = pathImportCase(t);
    c.publish({ 'common/pack.md': '---\nfrom: ../other-rules\npath: common\n---\n' });

    const result = await c.add();

    exits(result, 1);
    includes(result.stderr, 'context/common/pack.md');
    includes(result.stderr, '`path` alone');
  });

  test('path import of a folder holding its pack stops', async (t) => {
    const c = pathImportCase(t);
    c.publish({ 'common/pack.md': '---\npath: .\n---\n' });

    const result = await c.add();

    exits(result, 1);
    includes(result.stderr, 'overlap');
  });

  test('path import in a folder on disk reads its repo where it is', async (t) => {
    const c = pathImportCase(t);
    const result = await c.sync('add', 'house-rules', '../house-rules', '--path', 'context');

    exits(result, 0);
    includes(
      c.agents(),
      HEADER +
        '\n<!-- context-packs:pack house-rules -->\nPrefer small PRs.\n\n' +
        '<!-- context-packs:pack house-rules/common -->\nUse tabs.\n\n' +
        '## house-rules/common context\n\n' +
        '| When | Read |\n|---|---|\n| Styling code | `../house-rules/common/style.md` |\n',
    );
    assert.ok(!exists(c.gen));
  });
});

/** Two packs from one repo pointing at the same folder of it, such as web and api both including typescript. */
class SharedFolderCase extends SyncCase {
  constructor(t: TestContext) {
    super(t);
    this.publish({
      'web/pack.md': 'Build UI from components.\n',
      'web/typescript/pack.md': '---\npath: context/typescript\n---\n',
      'api/pack.md': 'Return problem+json errors.\n',
      'api/typescript/pack.md': '---\npath: context/typescript\n---\n',
      'typescript/pack.md': doc('Editing `**/*.ts`', 'Prefer unions.\n'),
    });
  }

  addPack(name: string) {
    return this.sync('add', name, this.origin, '--path', `context/${name}`);
  }
}

describe('SharedFolderTests', () => {
  test('folder both point at renders in each', async (t) => {
    const c = new SharedFolderCase(t);
    await c.addPack('web');

    const result = await c.addPack('api');

    exits(result, 0);
    includes(c.agents(), '| Editing `**/*.ts` | `context-packs/gen/api/typescript/pack.md` |\n');
    includes(c.agents(), '| Editing `**/*.ts` | `context-packs/gen/web/typescript/pack.md` |\n');
    assert.ok(exists(path.join(c.gen, 'api', 'typescript', 'pack.md')));
    assert.ok(exists(path.join(c.gen, 'web', 'typescript', 'pack.md')));
  });

  test('folder both point at renders in each at its holders ref', async (t) => {
    const c = new SharedFolderCase(t);
    await c.addPack('web');
    c.publish({ 'typescript/pack.md': doc('Editing `**/*.ts`', 'Prefer unions, never enums.\n') });

    const result = await c.addPack('api');

    exits(result, 0);
    assert.equal(read(path.join(c.gen, 'web', 'typescript', 'pack.md')), 'Prefer unions.\n');
    assert.equal(read(path.join(c.gen, 'api', 'typescript', 'pack.md')), 'Prefer unions, never enums.\n');
  });

  test('pack pointing at its own folder stops', async (t) => {
    const c = new SharedFolderCase(t);
    c.publish({ 'web/self/pack.md': '---\npath: context/web\n---\n' });

    const result = await c.addPack('web');

    exits(result, 1);
    includes(result.stderr, 'overlap');
  });
});
