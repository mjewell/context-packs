import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { describe, test } from 'node:test';

import { Case } from './case.ts';
import { exits, includes } from './expect.ts';
import { packedBin } from './package.ts';
import { run } from './scripts.ts';
import { tempDir } from './temp.ts';

/** A folder that reads as a repo, for the bin to sync. */
class NpmCase extends Case {
  repo!: string;

  protected override async setUp(): Promise<void> {
    await super.setUp();
    this.repo = tempDir(this.t, 'context-packs-test-');
    fs.mkdirSync(path.join(this.repo, '.git'));
  }
}

/** The npm package's bin, which npx runs, runs the CLI that packing the package compiled. */
describe("the npm package's bin", () => {
  const bin = packedBin();

  test('bin runs the cli in the current folder', async (t) => {
    const cwd = (await NpmCase.make(t)).repo;
    const result = await run(['node', bin.path], { cwd, timeout: 30_000 });

    exits(result, 0);
    assert.ok(fs.readFileSync(path.join(cwd, 'AGENTS.md'), 'utf8').startsWith('<!-- context-packs:start -->\n'));
  });

  test('bin passes the clis failure through', async (t) => {
    const cwd = (await NpmCase.make(t)).repo;
    const result = await run(['node', bin.path, 'remove', 'acme'], { cwd, timeout: 30_000 });

    exits(result, 1);
    includes(result.stderr, 'context-packs: ');
    includes(result.stderr, 'acme');
  });
});
