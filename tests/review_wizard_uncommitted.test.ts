import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { describe, test } from 'node:test';

import { exits, includes } from './expect.ts';
import { WizardCase } from './review_wizard_case.ts';

/**
 * A checkout with uncommitted changes of every kind: an edit staged, an edit not staged, a deletion, an untracked
 * file, and an ignored one.
 */
class DirtyCase extends WizardCase {
  protected override async setUp(): Promise<void> {
    await super.setUp();
    this.write('src/staged.py', 'y = 1\n');
    this.git('add', 'src/staged.py');
    this.write('src/app.py', 'x = 3\n');
    fs.rmSync(path.join(this.repo, 'tests/test_app.py'));
    this.write('src/new.py', 'z = 1\n');
    this.write('.gitignore', 'build/\n');
    this.write('build/out.txt', 'built\n');
  }

  write(file: string, text: string): void {
    fs.mkdirSync(path.dirname(path.join(this.repo, file)), { recursive: true });
    fs.writeFileSync(path.join(this.repo, file), text);
  }

  /** What git says about the checkout: its branch and commit, what's staged, and every file's status. */
  checkout(): string[] {
    return [
      this.git('symbolic-ref', 'HEAD'),
      this.git('rev-parse', 'HEAD'),
      this.git('diff', '--cached', '--name-status'),
      this.git('status', '--porcelain', '--ignored'),
    ];
  }

  /** init on the uncommitted changes, from HEAD. The run folder it made, once it succeeded. */
  async initUncommitted(): Promise<string> {
    const result = await this.wizard('init', '--base', 'HEAD', '--uncommitted', '--command', 'review');
    assert.equal(result.status, 0, result.stderr);
    this.runDir = /review --run (\S+) /.exec(result.stdout)![1]!;
    return result.stdout;
  }
}

/** init --uncommitted reviews the working files as a commit made from them, without changing the checkout. */
describe('init on uncommitted changes', () => {
  // The snapshot holds the edited rules, so they are the head's rules, and there's nothing to warn about.
  test('lists no rule files with uncommitted changes', async (t) => {
    const c = await DirtyCase.make(t);
    c.write('docs/testing.md', '# Testing\n\nMock nothing.\n');

    const out = await c.initUncommitted();

    assert.ok(!out.includes('uncommitted changes'), out);
  });

  test('reviews every uncommitted change but ignored files', async (t) => {
    const c = await DirtyCase.make(t);
    await c.initUncommitted();

    const files = await c.wizard('--run', c.runDir, 'files');

    exits(files, 0);
    assert.deepEqual(
      files.stdout
        .trim()
        .split('\n')
        .map((line) => line.split('\t')[1]),
      ['.gitignore', 'src/app.py', 'src/new.py', 'src/staged.py', 'tests/test_app.py'],
    );
    includes((await c.wizard('--run', c.runDir, 'diff', 'src/app.py')).stdout, '+x = 3');
  });

  test('leaves the branch, the index and the working files as they were', async (t) => {
    const c = await DirtyCase.make(t);
    const before = c.checkout();

    await c.initUncommitted();

    assert.deepEqual(c.checkout(), before);
    assert.equal(fs.readFileSync(path.join(c.repo, 'src/app.py'), 'utf8'), 'x = 3\n');
  });

  test('keeps reviewing the commit after the working files change', async (t) => {
    const c = await DirtyCase.make(t);
    await c.initUncommitted();
    c.write('src/app.py', 'x = 4\n');

    const diff = await c.wizard('--run', c.runDir, 'diff', 'src/app.py');

    includes(diff.stdout, '+x = 3');
  });

  test('refuses uncommitted with a head, and neither', async (t) => {
    const c = await DirtyCase.make(t);

    const both = await c.wizard('init', '--base', 'HEAD', '--head', 'HEAD', '--uncommitted', '--command', 'review');
    const neither = await c.wizard('init', '--base', 'HEAD', '--command', 'review');

    exits(both, 1);
    includes(both.stderr, 'Give init --head or --uncommitted, not both.');
    exits(neither, 1);
    includes(neither.stderr, 'Give init --head, the commit to review, or --uncommitted, to review the working files.');
  });
});
