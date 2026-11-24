import fs from 'node:fs';
import path from 'node:path';
import { describe, test } from 'node:test';

import { excludes, exits, includes } from './expect.ts';
import { CLAUSE, doc, OUTSIDE_CLAUSE, read, SyncCase } from './sync_case.ts';

function rows(...pairs: [string, string][]): string {
  return `## Context\n\n| When | Read |\n|---|---|\n${pairs.map(([when, file]) => `| ${when} | \`${file}\` |\n`).join('')}`;
}

/** A repo whose .git is gone, so the folder is in no repo. */
class OutsideCase extends SyncCase {
  protected override async setUp(): Promise<void> {
    await super.setUp();
    fs.rmdirSync(path.join(this.repo, '.git'));
  }
}

/** A folder in no git repo, such as the one above the repos: sessions start anywhere, so rows are absolute. */
describe('OutsideRepoTests', () => {
  test('rows are absolute', async (t) => {
    const c = await OutsideCase.make(t);
    c.write('context-packs/testing.md', doc('Writing tests'));

    const result = await c.sync();

    exits(result, 0);
    includes(c.agents(), rows(['Writing tests', `${c.repo}/context-packs/testing.md`]));
  });

  test('header says doc paths start from the docs folder then where the session started', async (t) => {
    const c = await OutsideCase.make(t);
    const result = await c.sync();

    exits(result, 0);
    excludes(c.agents(), CLAUSE);
    includes(c.agents(), `read its doc. ${OUTSIDE_CLAUSE}The packs here`);
  });

  test('a nested packs index has absolute rows', async (t) => {
    const c = await OutsideCase.make(t);
    c.write('context-packs/web/pack.md', doc('Editing `web/**`'));
    c.write('context-packs/web/forms.md', doc('Building a form'));

    const result = await c.sync();

    exits(result, 0);
    includes(c.agents(), rows(['Editing `web/**`', `${c.repo}/context-packs/gen/web.md`]));
    includes(read(path.join(c.gen, 'web.md')), `| Building a form | \`${c.repo}/context-packs/web/forms.md\` |`);
  });
});

/**
 * A folder inside a repo, such as a package with its own AGENTS.md: sessions start at the repo root, so rows start
 * there too.
 */
describe('SubfolderTests', () => {
  test('rows start from the repo root', async (t) => {
    const c = await SyncCase.make(t);
    c.write('packages/web/context-packs/testing.md', doc('Writing tests'));

    const result = await c.sync('--dir', path.join(c.repo, 'packages', 'web'));

    exits(result, 0);
    includes(
      read(path.join(c.repo, 'packages', 'web', 'AGENTS.md')),
      rows(['Writing tests', 'packages/web/context-packs/testing.md']),
    );
  });

  test('header says paths start from the repo root', async (t) => {
    const c = await SyncCase.make(t);
    c.write('packages/web/context-packs/testing.md', doc('Writing tests'));

    const result = await c.sync('--dir', path.join(c.repo, 'packages', 'web'));

    exits(result, 0);
    includes(read(path.join(c.repo, 'packages', 'web', 'AGENTS.md')), `read its doc. ${CLAUSE}The packs here`);
  });

  test('a worktrees git file marks the repo root', async (t) => {
    const c = await SyncCase.make(t);
    fs.rmdirSync(path.join(c.repo, '.git'));
    c.write('.git', 'gitdir: /elsewhere/.git/worktrees/repo\n');
    c.write('packages/web/context-packs/testing.md', doc('Writing tests'));

    const result = await c.sync('--dir', path.join(c.repo, 'packages', 'web'));

    exits(result, 0);
    includes(
      read(path.join(c.repo, 'packages', 'web', 'AGENTS.md')),
      rows(['Writing tests', 'packages/web/context-packs/testing.md']),
    );
  });
});
