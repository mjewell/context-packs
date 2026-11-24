import assert from 'node:assert/strict';
import fs from 'node:fs';
import { describe, test } from 'node:test';

import { excludes, exits, includes } from './expect.ts';
import { deviation, StartedCase, WizardCase } from './review_wizard_case.ts';
import { run, shell } from './scripts.ts';

/** A started run, and what brief prints for one finder. */
class BriefCase extends StartedCase {
  async brief(finder: string): Promise<string> {
    const result = await this.wizard('--run', this.runDir, 'brief', finder);
    exits(result, 0);
    return result.stdout;
  }
}

/**
 * brief gives one finder its prompt: the skill's prompt for its kind of finder, with the commands that read its docs
 * and the change, and where its answer goes.
 */
describe('brief', () => {
  test('names each of a units docs with the command that reads it', async (t) => {
    const c = await BriefCase.make(t);
    const brief = await c.brief('1');

    assert.ok(brief.startsWith("You're checking one unit of a pack review."), brief.slice(0, 80));
    includes(
      brief,
      `- \`docs/testing.md\`: run \`${c.command('doc', '1', '1')}\`\n` +
        `- \`docs/git.md\`: run \`${c.command('doc', '1', '2')}\`\n`,
    );
    excludes(brief, 'prose.md');
    includes(brief, 'Read each doc only through its command, so the review knows it was read.');
    includes(brief, `\`${c.command('files')}\``);
    includes(brief, `\`${c.command('diff', '<path>')}\``);
    includes(
      brief,
      'Run each command exactly as it is printed here, one per Bash call, with no variables, `cd` or ' +
        '`&&` around it.',
    );
    includes(brief, 'Read the code at the head in the current folder.');
    excludes(brief, 'Grep');
    includes(
      brief,
      `Write your answer as JSON to \`${c.answerPath('unit-1.json')}\`, with your tool for writing ` +
        'files, not the shell. Then run exactly this command, and do what it prints:\n\n' +
        `${c.command('submit', '1')}\n\n` +
        'Your answer must fit this JSON Schema:\n\n{\n "type": "object",',
    );
    includes(brief, '"take"');
    for (const placeholder of ['{diff}', '{log}', '{docs}']) excludes(brief, placeholder);
  });

  test('gives the uncovered finder every units docs to search', async (t) => {
    const c = await BriefCase.make(t);
    const brief = await c.brief('3');

    assert.ok(
      brief.startsWith("You're looking for the choices a change makes that no rule covers"),
      brief.slice(0, 80),
    );
    includes(brief, '- `AGENTS.md`\n- `docs/testing.md`\n- `docs/git.md`\n- `docs/prose.md`\n');
    excludes(brief, c.command('doc'));
    includes(brief, 'Each choice is one finding of kind `uncovered choice`');
    includes(brief, `\`${c.answerPath('unit-3.json')}\``);
    includes(brief, `\n\n${c.command('submit', '3')}\n\n`);
  });

  test('refuses a finder init didnt name', async (t) => {
    const c = await BriefCase.make(t);
    const result = await c.wizard('--run', c.runDir, 'brief', '4');

    exits(result, 1);
    includes(result.stderr, 'There is no finder 4: init named finders 0 to 3.');
  });
});

/** doc prints one of a unit's docs, as the file is at the head. */
describe('doc', () => {
  test('prints the doc a units brief numbers', async (t) => {
    const c = await StartedCase.make(t);
    const result = await c.step('doc', '1', '2');

    exits(result, 0);
    assert.equal(result.stdout, '# Git\n\nSmall commits.\n');
  });

  test('refuses a doc the unit doesnt have', async (t) => {
    const c = await StartedCase.make(t);
    const result = await c.step('doc', '1', '3');

    exits(result, 1);
    includes(result.stderr, 'Unit 1 has 2 docs.');
  });

  test('refuses the uncovered finder which reads docs with its own tools', async (t) => {
    const c = await StartedCase.make(t);
    const result = await c.step('doc', '3', '1');

    exits(result, 1);
    includes(result.stderr, 'The uncovered finder has no docs to read through doc: search them in the current folder.');
  });
});

/**
 * The submit command a brief prints works as written, run through a shell, once the answer is where the brief says
 * to write it.
 */
describe('commands run through a shell', () => {
  test('the briefs submit command takes the answer the brief named through bash', async (t) => {
    const c = await WizardCase.make(t);
    const launcher = shell('review/wizard');
    const init = await c.wizard('init', '--base', c.base, '--head', 'HEAD', '--command', launcher);
    exits(init, 0);
    const brief = /Run `(.+ brief 3)`/.exec(init.stdout)![1]!;
    const text = (await run(['bash', '-c', brief], { cwd: c.repo, env: c.env })).stdout;
    const submit = /\n\n(.+ submit 3)\n/.exec(text)![1]!;
    const answer = /Write your answer as JSON to `(.+?)`/.exec(text)![1]!;
    fs.writeFileSync(
      answer,
      JSON.stringify({ findings: [{ ...deviation('Quote "{this}"'), kind: 'uncovered choice', rules: [] }] }),
    );

    const submitted = await run(['bash', '-c', submit], { cwd: c.repo, env: c.env });

    exits(submitted, 0);
    includes(submitted.stdout, "The uncovered finder's answer is in, with 1 finding.");
  });
});
