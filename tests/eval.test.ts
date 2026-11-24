import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { describe, type TestContext, test } from 'node:test';

import { excludes, exits, includes } from './expect.ts';
import { CLAUSE, doc, exists, read, SyncCase } from './sync_case.ts';

const FAKE = path.join(import.meta.dirname, 'fake_claude.ts');

interface Run {
  readonly args: string[];
  readonly cwd: string;
  readonly instructions: string;
  readonly files: string[];
}

/** A repo whose own docs have cases, run by `eval` against a fake claude on PATH. */
class EvalCase extends SyncCase {
  readonly log = path.join(this.root, 'claude.log');

  static async make(t: TestContext): Promise<EvalCase> {
    const c = new EvalCase(t);
    await c.setUp();
    return c;
  }

  protected async setUp(): Promise<void> {
    const bin = path.join(this.root, 'bin');
    fs.mkdirSync(bin);
    fs.writeFileSync(path.join(bin, 'claude'), `#!/bin/sh\nexec '${process.execPath}' '${FAKE}' "$@"\n`, {
      mode: 0o755,
    });
    Object.assign(this.env, { PATH: `${bin}${path.delimiter}${this.env.PATH}`, FAKE_CLAUDE_LOG: this.log });
    this.write('context-packs/testing.md', doc('Writing tests', 'Use factories.\n'));
    await this.sync();
  }

  cases(text: string, name = 'testing'): void {
    this.write(`context-packs/.evals/${name}.md`, text);
  }

  /** Each session the fake claude ran, as it logged it. */
  runs(): Run[] {
    return read(this.log)
      .split('\n')
      .filter(Boolean)
      .map((line) => JSON.parse(line) as Run);
  }
}

describe('EvalTests', () => {
  test('reads prompt whose doc gets read passes', async (t) => {
    const c = await EvalCase.make(t);
    c.cases('## Reads\n\n- Help me with writing tests for the parser\n');

    const result = await c.sync('eval');

    exits(result, 0);
    includes(result.stdout, '✓ testing.md  reads  Help me with writing tests for the parser');
    excludes(result.stdout, 'also read');
  });

  test('reads prompt whose doc isnt read fails', async (t) => {
    const c = await EvalCase.make(t);
    c.cases('## Reads\n\n- Rename a variable in the parser\n');

    const result = await c.sync('eval');

    exits(result, 1);
    includes(result.stdout, '✗ testing.md  reads  Rename a variable in the parser');
    includes(result.stdout, 'read no docs');
  });

  test('skips prompt whose doc gets read fails', async (t) => {
    const c = await EvalCase.make(t);
    c.cases('## Skips\n\n- Help me with writing tests for the parser\n');

    const result = await c.sync('eval');

    exits(result, 1);
    includes(result.stdout, '✗ testing.md  skips  Help me with writing tests for the parser');
    includes(result.stdout, 'read: context-packs/testing.md');
  });

  test('prompt that passes lists the other docs its session read', async (t) => {
    const c = await EvalCase.make(t);
    c.write('context-packs/releasing.md', doc('Releasing a version'));
    await c.sync();
    c.cases('## Reads\n\n- Help me with writing tests before releasing a version\n');
    c.cases('## Skips\n\n- Help me with writing tests\n', 'releasing');

    const result = await c.sync('eval');

    exits(result, 0);
    includes(
      result.stdout,
      '✓ testing.md  reads  Help me with writing tests before releasing a version\n' +
        '    also read: context-packs/releasing.md\n',
    );
    includes(
      result.stdout,
      '✓ releasing.md  skips  Help me with writing tests\n' + '    also read: context-packs/testing.md\n',
    );
  });

  test('lines indented under an item continue its prompt', async (t) => {
    const c = await EvalCase.make(t);
    c.cases(
      '## Reads\n\n- CI failed while writing tests\n  for the parser:\n\n  ```\n  FAIL parse\n  ```\n' +
        '- Help me with writing tests\n',
    );

    const result = await c.sync('eval');

    exits(result, 0);
    const prompts = c.runs().map((run) => run.args[1]);
    assert.ok(prompts.includes('CI failed while writing tests\nfor the parser:\n\n```\nFAIL parse\n```'), `${prompts}`);
    includes(result.stdout, '✓ testing.md  reads  CI failed while writing tests\n');
  });

  test('stray line in a case file stops naming it', async (t) => {
    const c = await EvalCase.make(t);
    c.cases('## Reads\n\n- Help me with writing tests\nfor the parser\n');

    const result = await c.sync('eval');

    exits(result, 1);
    includes(result.stderr, 'context-packs/.evals/testing.md:4');
    assert.ok(!exists(c.log));
  });

  test('sessions run read only in a fresh repo without the cases', async (t) => {
    const c = await EvalCase.make(t);
    c.cases('## Reads\n\n- Help me with writing tests\n');

    const result = await c.sync('eval');

    exits(result, 0);
    const [run] = c.runs();
    assert.ok(!run!.cwd.startsWith(c.root), run!.cwd);
    assert.ok(run!.files.includes('context-packs/testing.md'));
    assert.ok(run!.files.includes('.git/HEAD'));
    assert.deepEqual(
      run!.files.filter((f) => f.includes('.evals')),
      [],
    );
    for (const flags of [
      ['--output-format', 'stream-json'],
      ['--setting-sources', 'project'],
      ['--tools', 'Read,Glob,Grep'],
      ['--allowedTools', 'Read,Glob,Grep'],
      ['--strict-mcp-config'],
    ]) {
      includes(run!.args.join(' '), flags.join(' '));
    }
  });

  test('runs repeats each prompt and counts the passes', async (t) => {
    const c = await EvalCase.make(t);
    c.cases('## Reads\n\n- Help me with writing tests\n');

    const result = await c.sync('eval', '--runs', '3');

    exits(result, 0);
    assert.equal(c.runs().length, 3);
    includes(result.stdout, '✓ testing.md  reads  3/3  Help me with writing tests');
  });

  test('naming docs runs only their cases', async (t) => {
    const c = await EvalCase.make(t);
    c.write('context-packs/releasing.md', doc('Releasing a version'));
    await c.sync();
    c.cases('## Reads\n\n- Help me with writing tests\n');
    c.cases('## Reads\n\n- Help me with releasing a version\n', 'releasing');

    const result = await c.sync('eval', 'releasing.md');

    exits(result, 0);
    includes(result.stdout, '✓ releasing.md  reads  Help me with releasing a version\n');
    excludes(result.stdout, 'testing.md');
  });

  test('repo without cases says so', async (t) => {
    const c = await EvalCase.make(t);
    const result = await c.sync('eval');

    exits(result, 1);
    includes(result.stderr, 'no pack has eval prompts');
    assert.ok(!exists(c.log));
  });

  test('stale block stops before any session', async (t) => {
    const c = await EvalCase.make(t);
    c.cases('## Reads\n\n- Help me with writing tests\n');
    c.write('context-packs/testing.md', doc('Writing or changing tests'));

    const result = await c.sync('eval');

    exits(result, 1);
    includes(result.stderr, 'stale');
    assert.ok(!exists(c.log));
  });

  test('sessions use sonnet unless told otherwise', async (t) => {
    const c = await EvalCase.make(t);
    c.cases('## Reads\n\n- Help me with writing tests\n');

    await c.sync('eval');
    await c.sync('eval', '--model', 'haiku');

    const models = c.runs().map((run) => run.args[run.args.indexOf('--model') + 1]);
    assert.deepEqual(models, ['sonnet', 'haiku']);
  });

  test('session goes on after reading its doc', async (t) => {
    const c = await EvalCase.make(t);
    c.write('context-packs/upgrading.md', doc('Upgrading dependencies'));
    await c.sync();
    c.cases('## Reads\n\n- Help me with writing tests, then upgrading dependencies\n');

    const result = await c.sync('eval');

    exits(result, 0);
    includes(
      result.stdout,
      '✓ testing.md  reads  Help me with writing tests, then upgrading dependencies\n' +
        '    also read: context-packs/upgrading.md\n',
    );
  });

  test('session that errors shows its error instead of passing', async (t) => {
    const c = await EvalCase.make(t);
    c.cases('## Skips\n\n- Rename a variable in the parser\n');
    c.env.FAKE_CLAUDE_ERROR = "There's an issue with the selected model (sonnet).";

    const result = await c.sync('eval');

    exits(result, 1);
    includes(
      result.stdout,
      '! testing.md  skips  Rename a variable in the parser\n' +
        "    error: There's an issue with the selected model (sonnet).\n",
    );
    assert.equal(result.stdout.trimEnd().split('\n').at(-1), '1 of 1 errored');
  });

  test('runs that error alike show their error once and count no passes', async (t) => {
    const c = await EvalCase.make(t);
    c.cases('## Skips\n\n- Rename a variable in the parser\n');
    c.env.FAKE_CLAUDE_ERROR = 'Not logged in.';

    const result = await c.sync('eval', '--runs', '2');

    includes(
      result.stdout,
      '! testing.md  skips  0/2  Rename a variable in the parser\n' + '    error: Not logged in.\n1 of 1 errored\n',
    );
  });

  test('session that ends without a result shows what claude printed', async (t) => {
    const c = await EvalCase.make(t);
    c.cases('## Skips\n\n- Rename a variable in the parser\n');
    c.env.FAKE_CLAUDE_CRASH = 'TypeError: undefined is not a function';

    const result = await c.sync('eval');

    exits(result, 1);
    includes(
      result.stdout,
      '! testing.md  skips  Rename a variable in the parser\n' + '    error: TypeError: undefined is not a function\n',
    );
  });

  test('session that runs out of turns just ends', async (t) => {
    const c = await EvalCase.make(t);
    c.cases('## Skips\n\n- Rename a variable in the parser\n');
    c.env.FAKE_CLAUDE_MAX_TURNS = '1';

    const result = await c.sync('eval');

    assert.equal(result.status, 0, result.stdout);
    includes(result.stdout, '✓ testing.md  skips  Rename a variable in the parser');
  });

  test('json prints only one document of each prompt and its runs', async (t) => {
    const c = await EvalCase.make(t);
    c.write('context-packs/releasing.md', doc('Releasing a version'));
    await c.sync();
    c.cases(
      '## Reads\n\n- Help me with writing tests before releasing a version\n\n' + '## Skips\n\n- Rename a variable\n',
    );

    const result = await c.sync('eval', '--json', '--runs', '2');

    exits(result, 0);
    const output = JSON.parse(result.stdout);
    assert.equal(output.model, 'sonnet');
    assert.equal(output.runs, 2);
    const [reads, skips] = output.cases;
    assert.deepEqual(
      { doc: reads.doc, expect: reads.expect, prompt: reads.prompt, outcome: reads.outcome, passes: reads.passes },
      {
        doc: 'testing.md',
        expect: 'reads',
        prompt: 'Help me with writing tests before releasing a version',
        outcome: 'passed',
        passes: 2,
      },
    );
    assert.deepEqual(
      reads.runs.map((run: { read: string[] }) => run.read),
      [
        ['context-packs/releasing.md', 'context-packs/testing.md'],
        ['context-packs/releasing.md', 'context-packs/testing.md'],
      ],
    );
    assert.deepEqual(
      reads.runs.map((run: { error: string | null }) => run.error),
      [null, null],
    );
    assert.deepEqual([skips.prompt, skips.outcome], ['Rename a variable', 'passed']);
  });

  test('json gives each runs time and cost', async (t) => {
    const c = await EvalCase.make(t);
    c.cases('## Reads\n\n- Help me with writing tests\n\n## Skips\n\n- Rename a variable\n');

    const result = await c.sync('eval', '--json');

    const [reads, skips] = JSON.parse(result.stdout).cases.map((item: { runs: unknown[] }) => {
      assert.equal(item.runs.length, 1);
      return item.runs[0] as { cost_usd: number; duration_ms: number };
    });
    assert.deepEqual([reads.cost_usd, skips.cost_usd], [0.0123, 0.0123]);
    assert.ok(Number.isInteger(reads.duration_ms));
    assert.ok(Number.isInteger(skips.duration_ms));
  });

  test('json gives a sessions error and still exits 1', async (t) => {
    const c = await EvalCase.make(t);
    c.cases('## Skips\n\n- Rename a variable\n');
    c.env.FAKE_CLAUDE_ERROR = 'Not logged in.';

    const result = await c.sync('eval', '--json');

    exits(result, 1);
    const { cases } = JSON.parse(result.stdout);
    assert.equal(cases.length, 1);
    assert.deepEqual([cases[0].outcome, cases[0].runs[0].error], ['errored', 'Not logged in.']);
  });

  test('output says what runs then how it went', async (t) => {
    const c = await EvalCase.make(t);
    c.cases('## Reads\n\n- Help me with writing tests\n- Writing tests again, please\n');

    const result = await c.sync('eval', '--runs', '2');

    exits(result, 0);
    const lines = result.stdout.trimEnd().split('\n');
    assert.equal(lines[0], 'Running 2 prompts for 1 doc, 2 times each, in a copy of the repo, on sonnet…');
    assert.equal(lines.at(-1), '2 passed');
  });
});

/**
 * A pack's .evals/ at its root: its prompts run with that pack installed alone, plus everything inside it. For
 * context-packs/, the top-level pack, that's the whole repo.
 */
class PackCase extends EvalCase {
  static override async make(t: TestContext): Promise<PackCase> {
    const c = new PackCase(t);
    await c.setUp();
    c.write('rules/pack.md', 'Prefer small PRs.\n');
    c.write('rules/deploying.md', doc('Deploying to production'));
    c.write('rules/.evals/deploying.md', '## Reads\n\n- Help me with deploying to production\n');
    return c;
  }

  async install(): Promise<void> {
    this.write('context-packs/core/pack.md', '---\npath: rules\n---\n');
    await this.sync();
  }
}

describe('PackTests', () => {
  test('installed packs prompts run with only that pack', async (t) => {
    const c = await PackCase.make(t);
    await c.install();

    const result = await c.sync('eval', 'deploying.md');

    exits(result, 0);
    includes(result.stdout, '✓ rules/deploying.md  reads  Help me with deploying to production\n');
    const { files } = c.runs()[0]!;
    assert.ok(files.includes('context-packs/rules/pack.md'));
    assert.ok(!files.includes('context-packs/testing.md'));
  });

  test('copy is synced as a repo is', async (t) => {
    const c = await PackCase.make(t);
    await c.install();

    const result = await c.sync('eval', 'deploying.md');

    exits(result, 0);
    includes(c.runs()[0]!.instructions, CLAUSE);
  });

  test('pack without a fixture runs in an empty folder', async (t) => {
    const c = await PackCase.make(t);
    await c.install();

    await c.sync('eval', 'deploying.md');

    const files = c.runs()[0]!.files.filter((f) => f.split('/')[0] !== '.git');
    assert.deepEqual(files.sort(), [
      'AGENTS.md',
      'CLAUDE.md',
      'context-packs',
      'context-packs/rules',
      'context-packs/rules/pack.md',
    ]);
  });

  test('pack with a fixture runs in it with only that pack', async (t) => {
    const c = await PackCase.make(t);
    c.write('rules/.evals/fixture/src/app.ts', 'export {};\n');
    await c.install();

    const result = await c.sync('eval', 'deploying.md');

    exits(result, 0);
    const { files } = c.runs()[0]!;
    assert.ok(files.includes('src/app.ts'));
    assert.ok(!files.includes('context-packs/testing.md'));
    assert.deepEqual(
      files.filter((f) => f.includes('.evals')),
      [],
    );
  });

  test('pack not installed runs the same with pack', async (t) => {
    const c = await PackCase.make(t);
    const result = await c.sync('eval', '--pack', 'rules');

    exits(result, 0);
    includes(result.stdout, '✓ rules/deploying.md  reads  Help me with deploying to production\n');
  });

  test('top packs prompts test an installed packs doc within the whole repo', async (t) => {
    const c = await PackCase.make(t);
    await c.install();
    c.cases('## Reads\n\n- Help me with deploying to production\n', 'core/deploying');

    const result = await c.sync('eval', 'core/deploying.md');

    exits(result, 0);
    includes(result.stdout, '✓ core/deploying.md  reads  Help me with deploying to production\n');
    const { files } = c.runs()[0]!;
    assert.ok(files.includes('context-packs/testing.md'));
    assert.ok(files.includes('context-packs/core/pack.md'));
  });

  test('top packs fixture gets all of context packs', async (t) => {
    const c = await PackCase.make(t);
    await c.install();
    c.cases('## Reads\n\n- Help me with writing tests\n');
    c.write('context-packs/.evals/fixture/src/parse.ts', 'export const parse = () => 1;\n');

    const result = await c.sync('eval', 'testing.md');

    exits(result, 0);
    const { files } = c.runs()[0]!;
    assert.ok(files.includes('src/parse.ts'));
    assert.ok(files.includes('context-packs/testing.md'));
    assert.ok(files.includes('context-packs/core/pack.md'));
  });

  test('nested packs prompts run with only that nested pack', async (t) => {
    const c = await PackCase.make(t);
    c.write('context-packs/server/pack.md', doc('Editing the server'));
    c.write('context-packs/server/database.md', doc('Changing the database'));
    c.write(
      'context-packs/server/.evals/database.md',
      '## Reads\n\n- Editing the server: help me with changing the database\n',
    );
    await c.sync();

    const result = await c.sync('eval', 'database.md');

    exits(result, 0);
    includes(result.stdout, 'context-packs/server/database.md  reads');
    assert.ok(!c.runs()[0]!.files.includes('context-packs/testing.md'));
  });

  test('case file naming no doc in its pack stops', async (t) => {
    const c = await PackCase.make(t);
    c.write('rules/.evals/releasing.md', '## Reads\n\n- Help me with releasing\n');
    await c.install();

    const result = await c.sync('eval');

    exits(result, 1);
    includes(result.stderr, 'rules/.evals/releasing.md names no doc in rules');
    assert.ok(!exists(c.log));
  });

  test('linked fixture is copied like a folder', async (t) => {
    const c = await PackCase.make(t);
    c.write('shared/src/parse.ts', 'export const parse = () => 1;\n');
    fs.symlinkSync('../../shared', path.join(c.repo, 'rules', '.evals', 'fixture'));
    await c.install();

    const result = await c.sync('eval', 'deploying.md');

    exits(result, 0);
    assert.ok(c.runs()[0]!.files.includes('src/parse.ts'));
  });

  test('fixture with its own context packs stops', async (t) => {
    const c = await PackCase.make(t);
    c.write('rules/.evals/fixture/context-packs/pack.md', 'Its own rules.\n');
    await c.install();

    const result = await c.sync('eval');

    exits(result, 1);
    includes(result.stderr, 'has a context-packs/ folder of its own');
    assert.ok(!exists(c.log));
  });
});
