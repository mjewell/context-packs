import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { describe, test } from 'node:test';

import { exits, includes } from './expect.ts';
import { packedBin } from './package.ts';
import { WizardCase } from './review_wizard_case.ts';
import { run } from './scripts.ts';

/**
 * init sets up a run and tells the orchestrator which finders to start, one per unit and the uncovered finder, each
 * with the one-line prompt it gives that finder.
 */
describe('init', () => {
  test('names a finder for each unit and the uncovered finder', async (t) => {
    const c = await WizardCase.make(t);
    const out = await c.init();

    // A headless session ends with the orchestrator's turn, and takes any finder in the background with it.
    includes(
      out,
      'Start these 4 subagents now, in the foreground, all in one message, so they run at once and you ' +
        'wait for every answer. Give each exactly this prompt:',
    );
    includes(out, `unit 0, AGENTS.md: Run \`${c.command('brief', '0')}\` and follow what it says.`);
    includes(out, `unit 1, 2 docs: Run \`${c.command('brief', '1')}\` and follow what it says.`);
    includes(out, `unit 2, 1 doc: Run \`${c.command('brief', '2')}\` and follow what it says.`);
    includes(out, `the uncovered finder: Run \`${c.command('brief', '3')}\` and follow what it says.`);
    includes(out, `When all of them have answered, run \`${c.command('next')}\`.`);
    assert.ok(fs.statSync(c.runDir).isDirectory());
  });

  test('keeps the run apart from the folder agents write answers in', async (t) => {
    const c = await WizardCase.make(t);
    await c.init();
    const temp = c.env.TMPDIR!;

    assert.equal(path.dirname(c.runDir), path.join(temp, 'pack-review-runs'));
    assert.ok(fs.statSync(path.join(temp, 'pack-review-answers', path.basename(c.runDir))).isDirectory());
  });

  // The review reads the rules from the checkout, so an uncommitted edit to one is judged as the head's rule.
  test('lists the rule files with uncommitted changes', async (t) => {
    const c = await WizardCase.make(t);
    fs.appendFileSync(path.join(c.repo, 'docs/testing.md'), 'Mock nothing.\n');
    fs.appendFileSync(path.join(c.repo, 'AGENTS.md'), 'Keep it short.\n');
    fs.appendFileSync(path.join(c.repo, 'src/app.py'), 'y = 3\n');

    const out = await c.init();

    includes(
      out,
      'These rule files have uncommitted changes, which the review reads as the rules at the head. ' +
        'Show the user this list before you start the finders:\n  AGENTS.md\n  docs/testing.md\n\n',
    );
    assert.ok(!out.includes('src/app.py'), out);
  });

  test('lists no rule files when none has uncommitted changes', async (t) => {
    const c = await WizardCase.make(t);
    fs.appendFileSync(path.join(c.repo, 'src/app.py'), 'y = 3\n');

    const out = await c.init();

    assert.ok(!out.includes('uncommitted'), out);
  });

  test('refuses a change that touches no files', async (t) => {
    const c = await WizardCase.make(t);
    const result = await c.wizard('init', '--base', 'HEAD', '--head', 'HEAD', '--command', 'review');

    exits(result, 1);
    includes(result.stderr, 'The change from');
    includes(result.stderr, 'touches no files, so there is nothing to review.');
  });

  test('refuses a checkout that isnt the head', async (t) => {
    const c = await WizardCase.make(t);
    c.git('checkout', '-q', c.base);

    const result = await c.wizard('init', '--base', c.base, '--head', c.head, '--command', 'review');

    exits(result, 1);
    includes(
      result.stderr,
      `Stop, tell the user the checkout is ${c.base}, not the head, ${c.head}, and offer to check out the head.`,
    );
    assert.equal(result.stdout, '');
  });
});

/**
 * Claude Code's allow rule passes any arguments after the wizard's command, so the wizard takes only the ones it
 * names, spelled out.
 */
describe('arguments', () => {
  test('refuses an option cut short', async (t) => {
    const c = await WizardCase.make(t);
    const result = await c.wizard('init', '--base', c.base, '--head', 'HEAD', '--comm', 'review');

    exits(result, 2);
    includes(result.stderr, 'the following arguments are required: --command');
  });

  test('refuses an argument a step doesnt take', async (t) => {
    const c = await WizardCase.make(t);
    await c.init();

    const result = await c.wizard('--run', c.runDir, 'files', '--output=x');

    exits(result, 2);
    includes(result.stderr, 'unrecognized arguments: --output=x');
  });
});

/**
 * A run folder can be gone by the time a step names it, such as after the system clears TMPDIR, so a step on one
 * says so and how to start again.
 */
describe('a run folder that is gone', () => {
  test('refuses a step on a run folder that doesnt exist', async (t) => {
    const c = await WizardCase.make(t);
    await c.init();
    fs.rmSync(c.runDir, { recursive: true });

    const result = await c.wizard('--run', c.runDir, 'next');

    exits(result, 1);
    assert.equal(
      result.stderr,
      `There's no review run in ${c.runDir}: its folder is gone, or init never ` +
        'made it. Start a new review with init.\n',
    );
  });
});

/** A local review runs the wizard as `npx context-packs@<version> review`, from the npm package alone. */
describe('the wizard from the npm package', () => {
  const bin = packedBin();

  function packaged(c: WizardCase, ...args: string[]) {
    return run(['node', bin.path, 'review', ...args], { cwd: c.repo, env: c.env });
  }

  test('runs the wizards steps from the package', async (t) => {
    const c = await WizardCase.make(t);
    const init = await packaged(c, 'init', '--base', c.base, '--head', 'HEAD', '--command', 'review');
    exits(init, 0);
    c.runDir = /review --run (\S+) /.exec(init.stdout)![1]!;

    const brief = await packaged(c, '--run', c.runDir, 'brief', '1');

    exits(brief, 0);
    assert.ok(brief.stdout.startsWith("You're checking one unit of a pack review."), brief.stdout.slice(0, 80));
  });

  test('passes a refusal through', async (t) => {
    const c = await WizardCase.make(t);
    const result = await packaged(c, 'init', '--base', c.base, '--head', c.base, '--command', 'review');

    exits(result, 1);
    includes(result.stderr, 'Stop, tell the user the checkout is');
  });
});
