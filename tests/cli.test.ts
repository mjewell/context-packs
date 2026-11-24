import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { describe, test } from 'node:test';

import { excludes, exits, includes } from './expect.ts';
import { command, run } from './scripts.ts';
import {
  block,
  CLAUSE,
  doc,
  EMPTY,
  exists,
  git,
  HEADER,
  names,
  OUTSIDE_CLAUSE,
  packed,
  read,
  SyncCase,
} from './sync_case.ts';

describe('SyncTests', () => {
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

/** A pack published to its origin, which the repo hasn't added yet. */
class AddRemoveCase extends SyncCase {
  first = '';

  protected override async setUp(): Promise<void> {
    await super.setUp();
    this.first = this.share('Prefer small PRs.\n');
  }
}

describe('AddRemoveTests', () => {
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

/** The repo's own docs and rules, written in context-packs/ itself, and listed where they are. */
class RootCase extends SyncCase {
  protected override async setUp(): Promise<void> {
    await super.setUp();
    this.write('context-packs/project/deploy/index.md', doc('Deploying', 'Ship it.\n'));
    this.write('context-packs/project/design.md', doc('Changing the design', 'Keep it small.\n'));
  }
}

describe('RootTests', () => {
  test('docs in context packs are listed where they are', async (t) => {
    const c = await RootCase.make(t);
    const result = await c.sync();

    exits(result, 0);
    assert.equal(
      c.agents(),
      block(
        '## Context\n\n| When | Read |\n|---|---|\n' +
          '| Deploying | `context-packs/project/deploy/index.md` |\n' +
          '| Changing the design | `context-packs/project/design.md` |\n',
      ),
    );
    assert.ok(!exists(c.gen));
  });

  test('pack md in context packs is inlined before its table', async (t) => {
    const c = await RootCase.make(t);
    c.write('context-packs/pack.md', 'Use pnpm.\n');

    const result = await c.sync();

    exits(result, 0);
    includes(c.agents(), `${HEADER}\nUse pnpm.\n\n## Context\n`);
  });

  test('when on the pack md in context packs stops the sync', async (t) => {
    const c = await RootCase.make(t);
    c.write('context-packs/pack.md', doc('Working on anything', 'Use pnpm.\n'));

    const result = await c.sync();

    exits(result, 1);
    includes(result.stderr, 'context-packs/pack.md');
    includes(result.stderr, 'when');
  });

  test('editing a doc needs no resync', async (t) => {
    const c = await RootCase.make(t);
    await c.sync();
    const before = read(c.agentsMd);
    c.write('context-packs/project/design.md', doc('Changing the design', 'Keep it smaller.\n'));

    const result = await c.sync();

    exits(result, 0);
    assert.equal(read(c.agentsMd), before);
  });

  test('new doc joins the table on resync', async (t) => {
    const c = await RootCase.make(t);
    await c.sync();
    c.write('context-packs/project/billing.md', doc('Editing billing', 'Charge once.\n'));

    const result = await c.sync();

    exits(result, 0);
    includes(c.agents(), '| Editing billing | `context-packs/project/billing.md` |\n');
  });
});

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

describe('SiblingPackTests', () => {
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

describe('PackShapeTests', () => {
  test('doc is copied and listed', async (t) => {
    const c = await SyncCase.make(t);
    c.publish({ 'billing.md': doc('Billing', 'Charge once.\n') });

    const result = await c.add();

    exits(result, 0);
    assert.equal(read(path.join(c.gen, 'house-rules', 'billing.md')), doc('Billing', 'Charge once.\n'));
    assert.equal(
      c.agents(),
      block(
        packed(
          'house-rules',
          '## house-rules context\n\n| When | Read |\n|---|---|\n' +
            '| Billing | `context-packs/gen/house-rules/billing.md` |\n',
        ),
      ),
    );
    assert.equal((await c.sync()).status, 0);
  });

  test('front matter key the tool doesnt know stops the sync', async (t) => {
    const c = await SyncCase.make(t);
    c.publish({ 'billing.md': doc('Billing', 'Charge once.\n', { owner: 'payments' }) });

    const result = await c.add();

    exits(result, 1);
    includes(result.stderr, 'context/billing.md');
    includes(result.stderr, 'owner');
    assert.ok(!exists(c.agentsMd));
    assert.ok(!exists(c.packs));
  });
});

/** A pack added at its origin's latest commit, which is pinned. */
class PinningCase extends SyncCase {
  pinned = '';

  protected override async setUp(): Promise<void> {
    await super.setUp();
    this.pinned = this.share('Prefer small PRs.\n');
    await this.add();
  }
}

describe('PinningTests', () => {
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

describe('VersionTests', () => {
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

/** house-rules added, and a second pack, acme, published from another origin's plugins/x. */
class SeveralCase extends SyncCase {
  acmeOrigin = '';
  acme = '';
  acmeRef = '';

  protected override async setUp(): Promise<void> {
    await super.setUp();
    this.share('Prefer small PRs.\n');
    await this.add();
    [this.acmeOrigin, this.acme] = this.remote('acme');
    this.acmeRef = this.publish(
      { 'pack.md': 'Use acme.\n', 'deploy.md': doc('Deploying', 'Ship it.\n') },
      this.acme,
      'plugins/x',
    );
  }

  addAcme(...args: string[]) {
    return this.sync('add', 'acme', this.acmeOrigin, '--path', 'plugins/x', ...args);
  }
}

describe('SeveralPacksTests', () => {
  test('packs render in the order of their folders each between markers naming it', async (t) => {
    const c = await SeveralCase.make(t);
    const result = await c.addAcme();

    exits(result, 0);
    assert.equal(
      c.agents(),
      block(
        `${packed(
          'acme',
          'Use acme.\n\n## acme context\n\n| When | Read |\n|---|---|\n' +
            '| Deploying | `context-packs/gen/acme/deploy.md` |\n',
        )}\n${packed('house-rules', 'Prefer small PRs.\n')}`,
      ),
    );
    assert.equal(read(path.join(c.gen, 'acme', 'deploy.md')), doc('Deploying', 'Ship it.\n'));
  });

  test('update moves every pinned pack', async (t) => {
    const c = await SeveralCase.make(t);
    await c.addAcme();
    const latest = c.share('Prefer small PRs.\nWrite tests first.\n');
    const acmeLatest = c.publish({ 'pack.md': 'Use acme v2.\n' }, c.acme, 'plugins/x');

    const result = await c.sync('update');

    exits(result, 0);
    includes(c.agents(), 'Use acme v2.\n');
    assert.equal(c.pin(), latest);
    assert.equal(c.pin('acme'), acmeLatest);
  });

  test('update by id moves only that pack', async (t) => {
    const c = await SeveralCase.make(t);
    await c.addAcme();
    c.share('Prefer small PRs.\nWrite tests first.\n');
    const acmeLatest = c.publish({ 'pack.md': 'Use acme v2.\n' }, c.acme, 'plugins/x');

    const result = await c.sync('update', 'acme');

    exits(result, 0);
    assert.equal(c.pin(), git(c.source, 'rev-parse', 'HEAD~1'));
    assert.equal(c.pin('acme'), acmeLatest);
  });

  test('list shows every import pack without the packs nested in them', async (t) => {
    const c = await SeveralCase.make(t);
    const acmeRef = c.publish({ 'billing/pack.md': doc('Editing billing', 'Charge once.\n') }, c.acme, 'plugins/x');
    await c.addAcme();

    const result = await c.sync('list');

    exits(result, 0);
    assert.equal(
      result.stdout,
      `acme  ${c.acmeOrigin}  plugins/x @ ${acmeRef}\n` +
        `house-rules  ${c.origin}  context @ ${git(c.source, 'rev-parse', 'HEAD')}\n`,
    );
  });
});
