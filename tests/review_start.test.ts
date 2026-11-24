import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { describe, test } from 'node:test';
import { BASE, HEAD } from './fake_github.ts';
import { PairingCase } from './pairing_case.ts';
import { REVIEW } from './review_case.ts';
import { quote, split } from './shlex.ts';

const ANSWERS = '/runner/temp/runs/pack-review-answers';
const CLI = `node ${path.dirname(REVIEW)}/src/cli.ts`;

/**
 * The review job's agent runs the pack-findings skill, as a local review does, from the review's own checkout,
 * allowed only the commands the skill runs.
 */
class StartCase extends PairingCase {
  async start(...extra: string[]): Promise<Record<string, string>> {
    const run = await this.script('start', '--base', BASE, '--head', HEAD, '--answers', ANSWERS, ...extra);
    assert.equal(run.status, 0, run.stderr);
    return this.outputs();
  }

  async args(...extra: string[]): Promise<string[]> {
    return split((await this.start(...extra))['claude-args']!);
  }
}

function flag(args: readonly string[], name: string): string | undefined {
  return args[args.indexOf(name) + 1];
}

describe('start', () => {
  test('asks for the pack findings skill on the reviewed range', async (t) => {
    const c = await StartCase.make(t);
    assert.equal(
      (await c.start()).prompt,
      `Use the pack-findings skill on the commit range ${BASE}..${HEAD}, with the checkout CLI.`,
    );
  });

  test('loads the skill from the reviews checkout', async (t) => {
    const c = await StartCase.make(t);
    assert.equal(flag(await c.args(), '--plugin-dir'), path.dirname(REVIEW));
  });

  test('allows only the skill and the commands it runs', async (t) => {
    const c = await StartCase.make(t);
    const args = await c.args();

    assert.equal(flag(args, '--tools'), 'Read,Glob,Grep,Write,Bash,Agent,Skill');
    assert.deepEqual(flag(args, '--allowedTools')!.split(','), [
      'Skill(context-packs:pack-findings)',
      `Bash(${CLI} review:*)`,
      `Bash(${CLI} docs)`,
      'Bash(git rev-parse:*)',
      'Bash(git status:*)',
      `Edit(/${ANSWERS}/**)`,
    ]);
    assert.equal(flag(args, '--disallowedTools'), 'Read(./.git/**)');
    assert.ok(args.includes('--restricted'));
  });

  test('lets the agent write only in the answers folder', async (t) => {
    const c = await StartCase.make(t);
    // A headless run writes outside its working directory only with both: the folder added, and an Edit rule for it.
    const args = await c.args();

    assert.equal(flag(args, '--add-dir'), ANSWERS);
    assert.deepEqual(
      flag(args, '--allowedTools')!
        .split(',')
        .filter((rule) => rule.startsWith('Edit')),
      [`Edit(//${ANSWERS.slice(1)}/**)`],
    );
  });

  test('gives the agent no mcp server and no answer schema', async (t) => {
    const c = await StartCase.make(t);
    const args = await c.args();

    assert.ok(args.includes('--strict-mcp-config'));
    assert.ok(!args.includes('--mcp-config'));
    assert.ok(!args.includes('--json-schema'));
  });

  test('passes a model when given one', async (t) => {
    const c = await StartCase.make(t);
    assert.equal(flag(await c.args('--model', 'opus'), '--model'), 'opus');
    fs.writeFileSync(c.output, '');
    assert.ok(!(await c.args('--model', '')).includes('--model'));
  });

  test('quotes each value whole so any shell style parser reads it the same', async (t) => {
    const c = await StartCase.make(t);
    for (const value of await c.args()) {
      const quoted = quote(value);
      assert.ok(quoted === value || (quoted.startsWith("'") && quoted.split("'").length - 1 === 2), value.slice(0, 60));
    }
  });
});
