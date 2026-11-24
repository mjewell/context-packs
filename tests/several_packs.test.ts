import assert from 'node:assert/strict';
import path from 'node:path';
import { describe, test } from 'node:test';

import { exits, includes } from './expect.ts';
import { block, doc, git, packed, read, SyncCase } from './sync_case.ts';

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

describe('several packs', () => {
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
