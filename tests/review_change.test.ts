import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { describe, test } from 'node:test';

import { excludes, exits, includes } from './expect.ts';
import { GitCase, withoutGit } from './git_case.ts';
import { command, type Result, run } from './scripts.ts';
import { tempDir } from './temp.ts';

// An instruction file with an empty context-packs block, as a sync writes it, so the wizard has its one unit.
const AGENTS =
  '<!-- context-packs:start -->\n' +
  `<!-- context-packs:end sha256:${createHash('sha256').update('').digest('hex').slice(0, 12)} -->\n`;
const TWELVE = Array.from({ length: 12 }, (_, n) => `l${n + 1}\n`).join('');

/** A diff from its first hunk on, without the header, whose index line holds hashes. */
function body(diff: string): string {
  return diff.slice(diff.indexOf('@@'));
}

/**
 * A repo whose base has an instruction file, and the wizard reading the change from the base to the head, the way a
 * finder reads it.
 */
class ChangeCase extends GitCase {
  env!: NodeJS.ProcessEnv;
  runDir: string | null = null;

  protected override async setUp(): Promise<void> {
    await super.setUp();
    this.base = this.commit('Add the instruction file', { 'AGENTS.md': AGENTS });
    this.env = withoutGit({ TMPDIR: tempDir(this.t, 'context-packs-runs-') });
  }

  /** A wizard step for the change from the base to the head, starting the run on the first. */
  async step(...args: string[]): Promise<Result> {
    if (this.runDir === null) {
      const init = await this.wizard('init', '--base', this.base, '--head', 'HEAD', '--command', 'review');
      exits(init, 0);
      this.runDir = /review --run (\S+) /.exec(init.stdout)![1]!;
    }
    return this.wizard('--run', this.runDir, ...args);
  }

  wizard(...args: string[]): Promise<Result> {
    return run([...command('review/wizard'), ...args], { cwd: this.repo, env: this.env });
  }

  async text(...args: string[]): Promise<string> {
    const result = await this.step(...args);
    exits(result, 0);
    return result.stdout;
  }
}

/** files lists what the change touches, so a finder can pick what to read and how many pages each takes. */
describe('FilesTests', () => {
  test('lists each changed path with the lines in its diff', async (t) => {
    const c = await ChangeCase.make(t);
    c.commit('Add two files', { 'a.txt': 'one\ntwo\nthree\n', 'docs/b.md': 'b\n' });
    c.commit('Change one', { 'a.txt': 'one\n2\nthree\n' });

    // A new file's diff is six lines of header and a line for each line it holds.
    assert.equal(await c.text('files'), '9\ta.txt\n7\tdocs/b.md\n');
  });

  test('lists a rename as a deleted path and an added one', async (t) => {
    const c = await ChangeCase.make(t);
    c.commit('Add', { 'old.txt': 'x\n' });
    c.base = c.git('rev-parse', 'HEAD');
    c.git('mv', 'old.txt', 'new.txt');
    c.commit('Rename');

    assert.equal(await c.text('files'), '7\tnew.txt\n7\told.txt\n');
  });
});

/** The report reads the head lines each diff shows, since a review comment can be left only on one of them. */
describe('ShownTests', () => {
  test('prints the head lines each diff shows', async (t) => {
    const c = await ChangeCase.make(t);
    c.commit('Add', { 'a.txt': TWELVE, 'gone.txt': 'x\n' });
    c.base = c.git('rev-parse', 'HEAD');
    c.commit('Change line 10 and delete a file', { 'a.txt': TWELVE.replace('l10\n', 'ten\n') }, ['gone.txt']);

    const result = await run([...command('review/change'), '--base', c.base, '--head', 'HEAD', 'shown'], {
      cwd: c.repo,
    });

    exits(result, 0);
    assert.deepEqual(JSON.parse(result.stdout), { 'a.txt': [7, 8, 9, 10, 11, 12], 'gone.txt': [] });
  });
});

/**
 * diff shows one path's change, with each line the head has numbered as it is there, so a finding can name a line
 * without counting.
 */
describe('DiffTests', () => {
  test('numbers each line the head has and leaves removed lines blank', async (t) => {
    const c = await ChangeCase.make(t);
    c.commit('Add', { 'a.txt': TWELVE });
    c.base = c.git('rev-parse', 'HEAD');
    c.commit('Change line 10', { 'a.txt': TWELVE.replace('l10\n', 'ten\n') });

    const diff = await c.text('diff', 'a.txt');

    assert.ok(diff.startsWith('diff --git a/a.txt b/a.txt\n'), diff);
    assert.equal(
      body(diff),
      '@@ -7,6 +7,6 @@ l6\n' +
        ' 7  l7\n' +
        ' 8  l8\n' +
        ' 9  l9\n' +
        '   -l10\n' +
        '10 +ten\n' +
        '11  l11\n' +
        '12  l12\n',
    );
  });

  test('numbers each hunk from its own start', async (t) => {
    const c = await ChangeCase.make(t);
    c.commit('Add', { 'a.txt': TWELVE });
    c.base = c.git('rev-parse', 'HEAD');
    c.commit('Change both ends', { 'a.txt': `one\n${TWELVE.slice(3, -4)}twelve\n` });

    assert.equal(
      body(await c.text('diff', 'a.txt')),
      '@@ -1,4 +1,4 @@\n' +
        '   -l1\n' +
        ' 1 +one\n' +
        ' 2  l2\n' +
        ' 3  l3\n' +
        ' 4  l4\n' +
        '@@ -9,4 +9,4 @@ l8\n' +
        ' 9  l9\n' +
        '10  l10\n' +
        '11  l11\n' +
        '   -l12\n' +
        '12 +twelve\n',
    );
  });

  test('leaves the no newline marker unnumbered', async (t) => {
    const c = await ChangeCase.make(t);
    c.commit('Add', { 'a.txt': 'one\n' });
    c.base = c.git('rev-parse', 'HEAD');
    c.commit('Drop the newline', { 'a.txt': 'one\ntwo' });

    assert.equal(
      body(await c.text('diff', 'a.txt')),
      '@@ -1 +1,2 @@\n' + '1  one\n' + '2 +two\n' + '  \\ No newline at end of file\n',
    );
  });

  test('shows only the change since the merge base', async (t) => {
    const c = await ChangeCase.make(t);
    c.commit('Add', { 'a.txt': 'a\n', 'b.txt': 'b\n' });
    const fork = c.git('rev-parse', 'HEAD');
    c.git('checkout', '-q', '-b', 'base');
    c.base = c.commit('Change b on the base branch', { 'b.txt': 'base\n' });
    c.git('checkout', '-q', fork);
    c.commit('Change a on the PR', { 'a.txt': 'pr\n' });

    assert.equal(await c.text('files'), '7\ta.txt\n');
    includes((await c.step('diff', 'b.txt')).stderr, "b.txt isn't one of the paths");
  });

  test('refuses a path outside the change however it is written', async (t) => {
    const c = await ChangeCase.make(t);
    c.commit('Add', { 'a.txt': 'a\n' });

    for (const file of ['/etc/passwd', '../a.txt', 'docs/../a.txt', '..', '', '-p', '--output=x']) {
      const result = file.startsWith('-') ? await c.step('diff', '--', file) : await c.step('diff', file);

      assert.equal(result.status, 1, `${file}: ${result.stdout}`);
      includes(result.stderr, `${file} isn't one of the paths`, file);
    }
  });

  test('reads a path literally not as a pattern', async (t) => {
    const c = await ChangeCase.make(t);
    c.commit('Add a file named like a pattern', { '*.txt': 'star\n', 'b.txt': 'b\n' });

    const diff = await c.text('diff', '*.txt');

    includes(diff, '+star');
    excludes(diff, 'b.txt');
  });

  test('runs no external diff or textconv', async (t) => {
    const c = await ChangeCase.make(t);
    const script = path.join(path.dirname(c.repo), `${path.basename(c.repo)}-driver.sh`);
    const ran = path.join(path.dirname(c.repo), `${path.basename(c.repo)}-ran`);
    fs.writeFileSync(script, `#!/bin/sh\ntouch ${ran}\necho converted\n`, { mode: 0o755 });
    t.after(() => fs.rmSync(script, { force: true }));
    t.after(() => fs.rmSync(ran, { force: true }));
    c.git('config', 'diff.external', script);
    c.git('config', 'diff.conv.textconv', script);
    c.commit('Add', { '.gitattributes': '*.txt diff=conv\n', 'a.txt': 'a\n' });
    c.commit('Change', { 'a.txt': 'b\n' });

    await c.text('diff', 'a.txt');

    assert.ok(!fs.existsSync(ran));
  });
});

/** A change that adds a file of 2500 lines. */
class PagingCase extends ChangeCase {
  protected override async setUp(): Promise<void> {
    await super.setUp();
    this.commit('Add a long file', { 'long.txt': Array.from({ length: 2500 }, (_, n) => `${n + 1}\n`).join('') });
  }
}

/** Long output comes in pages of 1000 lines, so one step can't fill a finder's context. */
describe('PagingTests', () => {
  test('gives the first page and says how to get the next', async (t) => {
    const c = await PagingCase.make(t);
    const lines = (await c.text('diff', 'long.txt')).trimEnd().split('\n');

    assert.equal(lines.length, 1001);
    assert.equal(lines[999], ' 994 +994');
    assert.equal(lines[1000], '(page 1 of 3: run it again with page 2 for more)');
  });

  test('gives a later page', async (t) => {
    const c = await PagingCase.make(t);
    const lines = (await c.text('diff', 'long.txt', '3')).trimEnd().split('\n');

    // The diff has 2506 lines: six of header, then one per line of the file.
    assert.equal(lines[0], '1995 +1995');
    assert.deepEqual(lines.slice(-2), ['2500 +2500', '(page 3 of 3)']);
  });

  test('refuses a page past the last and one that isnt a page', async (t) => {
    const c = await PagingCase.make(t);
    includes((await c.step('diff', 'long.txt', '4')).stderr, 'long.txt has 3 pages.');
    for (const page of ['0', 'two', '-1']) {
      const result = await c.step('diff', 'long.txt', page);

      assert.equal(result.status, 1, page);
      includes(result.stderr, `'${page}' isn't a page: pages count from 1.`, page);
    }
  });
});

/** log lists the change's commits with their messages, since a message can say a choice was deliberate. */
describe('LogTests', () => {
  test('lists the changes commits newest first and none from the base branch', async (t) => {
    const c = await ChangeCase.make(t);
    c.commit('Add', { 'a.txt': 'a\n' });
    const fork = c.git('rev-parse', 'HEAD');
    c.git('checkout', '-q', '-b', 'base');
    c.base = c.commit('On the base branch', { 'b.txt': 'b\n' });
    c.git('checkout', '-q', fork);
    const first = c.commit('Change a\n\nThe reason.', { 'a.txt': 'x\n' });
    const second = c.commit('Add c', { 'c.txt': 'c\n' });

    const text = await c.text('log');

    assert.deepEqual(
      [...text.matchAll(/^commit (\w+)$/gm)].map((m) => m[1]),
      [second, first],
    );
    includes(text, '    Change a\n    \n    The reason.\n');
    excludes(text, 'On the base branch');
  });
});
