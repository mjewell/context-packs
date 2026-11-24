import assert from 'node:assert/strict';
import { describe, test } from 'node:test';

import { exits, includes } from './expect.ts';
import { DoneCase, MergeCase } from './review_wizard_case.ts';

/** The text after the wizard's "Here it is:" line, read as JSON. */
function printed(stdout: string): unknown {
  const listed = 'Here it is:\n';
  return JSON.parse(stdout.slice(stdout.indexOf(listed) + listed.length));
}

/**
 * pack-review goes through the findings one at a time. finding prints one, with what its kind means and what the user
 * decides about it, so the agent has the kind's text whichever way the findings came.
 */
describe('one finding', () => {
  test('prints a deviation with what the user decides about it', async (t) => {
    const c = await DoneCase.make(t);
    const result = await c.step('finding', '1');

    exits(result, 0);
    assert.ok(result.stdout.startsWith('Finding 1 of 3, a deviation.\n'), result.stdout.slice(0, 80));
    includes(result.stdout, 'A deviation is where the change goes against a written rule.');
    includes(result.stdout, "When the rule's doc wasn't routed, its `when` may also need fixing");
    assert.deepEqual(printed(result.stdout), c.findings()[0]);
  });

  test('prints a conflict with what the user decides about it', async (t) => {
    const c = await DoneCase.make(t);
    const result = await c.step('finding', '2');

    exits(result, 0);
    assert.ok(result.stdout.startsWith('Finding 2 of 3, a conflict.\n'), result.stdout.slice(0, 80));
    includes(result.stdout, 'A conflict is where two rules point opposite ways at the same spot.');
    includes(result.stdout, 'Ask the user which rule wins.');
    assert.deepEqual(printed(result.stdout), c.findings()[1]);
  });

  test('prints an uncovered choice with what the user decides about it', async (t) => {
    const c = await DoneCase.make(t);
    const result = await c.step('finding', '3');

    exits(result, 0);
    assert.ok(result.stdout.startsWith('Finding 3 of 3, an uncovered choice.\n'), result.stdout.slice(0, 80));
    includes(result.stdout, 'no rule covers it.');
    includes(result.stdout, 'Ask the user whether to write a rule for it, and which way new code should follow.');
    assert.deepEqual(printed(result.stdout), c.findings()[2]);
  });

  test('refuses a finding the review doesnt have', async (t) => {
    const c = await DoneCase.make(t);
    for (const n of ['0', '4', 'one']) {
      const result = await c.step('finding', n);

      exits(result, 1);
      assert.equal(result.stderr, `There is no finding ${n}: the review has 3 findings, numbered from 1.\n`);
    }
  });

  test('refuses a finding before the review is done', async (t) => {
    const c = await MergeCase.make(t);
    await c.allIn();
    const result = await c.step('finding', '1');

    exits(result, 1);
    assert.equal(
      result.stderr,
      `The review has no findings yet: run \`${c.command('next')}\` to see what it's waiting on.\n`,
    );
  });
});
