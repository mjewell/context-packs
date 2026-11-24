import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { describe, test } from 'node:test';

import { exits, includes } from './expect.ts';
import { spot } from './review_case.ts';
import { deviation, SubmitCase } from './review_wizard_case.ts';

interface Source {
  readonly id: string;
  readonly finding: { readonly headline: string };
}

/** next tells the orchestrator what to do now, from what the run folder holds, so it can also pick a run back up. */
describe('next', () => {
  test('names each finder whose answer isnt in with its prompt', async (t) => {
    const c = await SubmitCase.make(t);
    await c.submitUnit(0, 1, []);
    await c.submitUnit(2, 1, []);

    const result = await c.step('next');

    exits(result, 0);
    assert.equal(
      result.stdout,
      "Waiting on 2 finders, whose answers aren't in yet:\n" +
        `  unit 1, 2 docs: Run \`${c.command('brief', '1')}\` and follow what it says.\n` +
        `  the uncovered finder: Run \`${c.command('brief', '3')}\` and follow what it says.\n` +
        'If one of them stopped without its answer going in, start it again in the foreground, with the same ' +
        'prompt. ' +
        `When they have all answered, run \`${c.command('next')}\` again.\n`,
    );
  });

  test('starts the merge once every finder is in and numbers their findings', async (t) => {
    const c = await SubmitCase.make(t);
    await c.submitUnit(0, 1, [deviation('A')]);
    await c.submitUnit(1, 2, [deviation('B'), deviation('C')]);
    await c.submitUnit(2, 1, []);
    assert.equal((await c.submit(3, [{ ...deviation('D'), kind: 'uncovered choice', rules: [] }])).status, 0);

    const result = await c.step('next');

    exits(result, 0);
    assert.equal(
      result.stdout,
      'All 4 finders are in, with 4 findings.\n' +
        'Start one subagent in the foreground, with exactly this prompt: Run ' +
        `\`${c.command('brief', 'merge')}\` and follow what it says.\n` +
        `When it has answered, run \`${c.command('next')}\`.\n`,
    );
    const sources: Source[] = JSON.parse(fs.readFileSync(path.join(c.runDir, 'sources.json'), 'utf8'));
    assert.deepEqual(
      sources.map((source) => [source.id, source.finding.headline]),
      [
        ['0:0', 'A'],
        ['1:0', 'B'],
        ['1:1', 'C'],
        ['3:0', 'D'],
      ],
    );
  });

  test('keeps the finders answers once the merge has started', async (t) => {
    const c = await SubmitCase.make(t);
    for (const [unit, docs] of [
      [0, 1],
      [1, 2],
      [2, 1],
    ] as const) {
      await c.submitUnit(unit, docs, []);
    }
    await c.submit(3, []);
    await c.step('next');

    const result = await c.submit(1, []);

    exits(result, 1);
    includes(result.stderr, "Not taken: the merge has started, so the finders' answers can't change.");
  });
});

/** Every finder in: units 0 and 1 with one deviation each, unit 2 with none, and the uncovered finder with one. */
class MergeCase extends SubmitCase {
  async allIn(): Promise<void> {
    await this.submitUnit(0, 1, [deviation('A')]);
    await this.submitUnit(1, 2, [deviation('B')]);
    await this.submitUnit(2, 1, []);
    assert.equal((await this.submit(3, [{ ...deviation('D'), kind: 'uncovered choice', rules: [] }])).status, 0);
    assert.equal((await this.step('next')).status, 0);
  }
}

/**
 * Once every finder is in, one subagent groups their findings, and the wizard builds the findings from its groups, as
 * the merge job's script does.
 */
describe('the merge', () => {
  test('brief gives the merging agent the numbered findings and where its groups go', async (t) => {
    const c = await MergeCase.make(t);
    await c.allIn();

    const result = await c.step('brief', 'merge');

    exits(result, 0);
    assert.ok(
      result.stdout.startsWith("You're merging the finders' answers in a pack review"),
      result.stdout.slice(0, 80),
    );
    includes(result.stdout, `Every finder's findings, each with an id, are what \`${c.command('sources')}\` prints.`);
    includes(
      result.stdout,
      `Write your groups as JSON to \`${c.answerPath('groups.json')}\`, with your tool for writing ` +
        'files, not the shell. Then run exactly this command, and do what it prints:\n\n' +
        `${c.command('submit-groups')}\n\n` +
        'Your groups must fit this JSON Schema:\n\n{\n "type": "object",',
    );
    includes(result.stdout, 'Run each command exactly as it is printed here');
    includes(result.stdout, '"ids"');
  });

  test('sources prints the finders findings numbered', async (t) => {
    const c = await MergeCase.make(t);
    await c.allIn();

    const result = await c.step('sources');

    exits(result, 0);
    assert.deepEqual(
      (JSON.parse(result.stdout) as Source[]).map((source) => [source.id, source.finding.headline]),
      [
        ['0:0', 'A'],
        ['1:0', 'B'],
        ['3:0', 'D'],
      ],
    );
  });

  test('sources refuses before every finder is in', async (t) => {
    const c = await MergeCase.make(t);
    const result = await c.step('sources');

    exits(result, 1);
    includes(result.stderr, `The merge can't start yet: run \`${c.command('next')}\` to see whose answers aren't in.`);
  });

  test('brief refuses the merge before every finder is in', async (t) => {
    const c = await MergeCase.make(t);
    const result = await c.step('brief', 'merge');

    exits(result, 1);
    includes(result.stderr, `The merge can't start yet: run \`${c.command('next')}\` to see whose answers aren't in.`);
  });

  test('next waits on the merge until its groups are in', async (t) => {
    const c = await MergeCase.make(t);
    await c.allIn();

    const result = await c.step('next');

    assert.equal(
      result.stdout,
      "Waiting on the merge, whose groups aren't in yet. If it stopped without its " +
        'groups going in, start it again in the foreground, with the same prompt: Run ' +
        `\`${c.command('brief', 'merge')}\` and follow what it says. When it has ` +
        `answered, run \`${c.command('next')}\` again.\n`,
    );
  });

  test('refuses groups that leave out a finders finding', async (t) => {
    const c = await MergeCase.make(t);
    await c.allIn();
    const result = await c.submitGroups([{ ids: ['0:0', '1:0'], kind: 'deviation', headline: 'H', take: 'T' }]);

    exits(result, 1);
    includes(
      result.stderr,
      "Not taken: the merge's groups leave out 3:0. Fix your groups, then submit them again with " +
        `\`${c.command('submit-groups')}\`.`,
    );
  });

  test('builds the findings from the groups and next says its done', async (t) => {
    const c = await MergeCase.make(t);
    await c.allIn();
    const result = await c.submitGroups([
      { ids: ['0:0', '1:0'], kind: 'deviation', headline: 'One import, two rules', take: 'T' },
      { ids: ['3:0'], kind: 'uncovered choice', headline: 'Where config lives', take: 'U' },
    ]);

    exits(result, 0);
    const file = `${c.runDir}/findings.json`;
    assert.equal(result.stdout, `2 findings are in ${file}. Tell whoever started you, and stop.\n`);
    const report = JSON.parse(fs.readFileSync(file, 'utf8'));
    assert.deepEqual([report.base, report.head], [c.base, c.head]);
    assert.deepEqual(
      report.findings.map((found: { headline: string; rules: unknown[]; take: string }) => [
        found.headline,
        found.rules.length,
        found.take,
      ]),
      [
        ['One import, two rules', 1, 'T'],
        ['Where config lives', 0, 'U'],
      ],
    );
    const done = (await c.step('next')).stdout;
    const split = done.indexOf('\n');
    assert.equal(
      done.slice(0, split),
      `Done: 2 findings, 1 deviation and 1 uncovered choice, in ${file}. Here they are:`,
    );
    assert.deepEqual(JSON.parse(done.slice(split + 1)), report.findings);
  });

  test('refuses groups once the findings are built and keeps them', async (t) => {
    const c = await MergeCase.make(t);
    await c.allIn();
    exits(await c.submitGroups([{ ids: ['0:0', '1:0', '3:0'], kind: 'deviation', headline: 'First', take: 'T' }]), 0);
    const file = path.join(c.runDir, 'findings.json');
    const before = fs.readFileSync(file, 'utf8');

    for (const groups of [
      [{ ids: ['0:0', '1:0', '3:0'], kind: 'deviation', headline: 'First', take: 'T' }],
      [{ ids: ['0:0', '1:0', '3:0'], kind: 'deviation', headline: 'Second', take: 'T' }],
      [{ ids: ['0:0'], kind: 'deviation', headline: 'Third', take: 'T' }],
    ]) {
      const result = await c.submitGroups(groups);

      exits(result, 1);
      assert.equal(
        result.stderr,
        "Not taken: the findings are already built, so the groups can't change. Tell whoever started you, and stop.\n",
      );
      assert.equal(fs.readFileSync(file, 'utf8'), before);
    }
  });
});

const NUMBERS = { file: 'AGENTS.md', quote: 'Game numbers live in content.', routed: true };
const SIM = { file: 'docs/testing.md', quote: 'Sim code reads its numbers from content.', routed: false };

function found({
  rules = [] as readonly unknown[],
  spots = [] as readonly unknown[],
  deliberate = [] as readonly string[],
  exemplars = [] as readonly unknown[],
  kind = 'deviation',
  headline = 'A finder headline',
} = {}) {
  return {
    kind,
    headline,
    rules: [...rules],
    spots: [...spots],
    deliberate: [...deliberate],
    exemplars: [...exemplars],
    take: 'A finder take.',
  };
}

function group(
  ids: readonly string[],
  { kind = 'deviation', headline = 'A game number in sim code', take = 'Move it to content.' } = {},
) {
  return { ids: [...ids], kind, headline, take };
}

/** A run whose groups the tests choose, and the findings the wizard builds from them. */
class GroupCase extends SubmitCase {
  /** Every finder in, with these findings: unit 0's are 0:0, 0:1 and so on. */
  async answered({
    unit0 = [] as readonly unknown[],
    unit1 = [] as readonly unknown[],
    unit2 = [] as readonly unknown[],
    uncovered = [] as readonly unknown[],
  } = {}): Promise<void> {
    for (const [unit, docs, findings] of [
      [0, 1, unit0],
      [1, 2, unit1],
      [2, 1, unit2],
    ] as const) {
      await this.submitUnit(unit, docs, findings);
    }
    assert.equal((await this.submit(3, uncovered)).status, 0);
    assert.equal((await this.step('next')).status, 0);
  }

  async built(groups: readonly unknown[]) {
    const result = await this.submitGroups(groups);
    exits(result, 0);
    return JSON.parse(fs.readFileSync(path.join(this.runDir, 'findings.json'), 'utf8')).findings;
  }
}

/**
 * Each finding is built from the finders' findings its group names, so the merge can't drop what they found, and
 * groups that would drop, repeat or invent one are refused.
 */
describe("the merge's groups", () => {
  test('builds a finding from every finding its group names', async (t) => {
    const c = await GroupCase.make(t);
    await c.answered({
      unit0: [found({ rules: [NUMBERS], spots: [spot('src/sim.ts', 42)], deliberate: ['Commit abc says so.'] })],
      unit2: [
        found({
          rules: [SIM, NUMBERS],
          spots: [spot('src/sim.ts', 42), spot('src/rng.ts', 9)],
          deliberate: ['Commit abc says so.', 'A comment at the spot.'],
        }),
      ],
    });

    const findings = await c.built([group(['0:0', '2:0'])]);

    assert.deepEqual(findings, [
      {
        kind: 'deviation',
        headline: 'A game number in sim code',
        take: 'Move it to content.',
        rules: [NUMBERS, SIM],
        spots: [spot('src/sim.ts', 42), spot('src/rng.ts', 9)],
        deliberate: ['Commit abc says so.', 'A comment at the spot.'],
        exemplars: [],
      },
    ]);
  });

  test('counts a spot as deviating when any finding says it deviates', async (t) => {
    const c = await GroupCase.make(t);
    await c.answered({
      unit0: [found({ rules: [NUMBERS], spots: [spot('src/sim.ts', 42)] })],
      unit1: [found({ rules: [SIM], spots: [spot('src/sim.ts', 42, true)] })],
    });

    const [finding] = await c.built([group(['0:0', '1:0'], { kind: 'conflict' })]);

    assert.equal(finding.kind, 'conflict');
    assert.deepEqual(finding.spots, [spot('src/sim.ts', 42)]);
  });

  test('keeps an uncovered choices exemplars in the finding that holds it', async (t) => {
    const c = await GroupCase.make(t);
    const ways = [{ way: 'Loaded at startup', examples: ['src/load.ts:8'] }];
    await c.answered({
      unit0: [found({ rules: [NUMBERS], spots: [spot('src/load.ts', 3)] })],
      uncovered: [found({ kind: 'uncovered choice', spots: [spot('src/load.ts', 3)], exemplars: ways })],
    });

    const [finding] = await c.built([group(['0:0', '3:0'])]);

    assert.deepEqual(finding.exemplars, ways);
    assert.deepEqual(finding.rules, [NUMBERS]);
  });

  test('keeps the groups in the order the agent gave them', async (t) => {
    const c = await GroupCase.make(t);
    await c.answered({ unit0: [found()], unit1: [found()] });

    const findings = await c.built([group(['1:0'], { headline: 'Second' }), group(['0:0'], { headline: 'First' })]);

    assert.deepEqual(
      findings.map((f: { headline: string }) => f.headline),
      ['Second', 'First'],
    );
  });

  test('refuses groups that leave out repeat or invent a finders finding', async (t) => {
    const c = await GroupCase.make(t);
    await c.answered({ unit0: [found()], unit1: [found()] });
    for (const [groups, says] of [
      [[group(['0:0'])], 'leave out 1:0'],
      [[group(['0:0', '1:0']), group(['1:0'])], 'put 1:0 in more than one group'],
      [[group(['0:0', '1:0', '9:9'])], 'name 9:9, which no finder reported'],
    ] as const) {
      const result = await c.submitGroups(groups);

      assert.equal(result.status, 1, says);
      includes(result.stderr, says);
      assert.ok(!fs.existsSync(path.join(c.runDir, 'findings.json')), says);
    }
  });
});
