import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { describe, test } from 'node:test';

import { exits, includes } from './expect.ts';
import { deviation, SubmitCase } from './review_wizard_case.ts';

/**
 * submit takes a finder's answer only when it's whole: in the schema's shape, and after every doc of its unit was read
 * through doc. A refusal says what to do, then to submit again.
 */
describe('submit', () => {
  test('takes an answer once every doc was read', async (t) => {
    const c = await SubmitCase.make(t);
    await c.readDocs(1, 2);

    const result = await c.submit(1, [deviation()]);

    exits(result, 0);
    assert.equal(
      result.stdout,
      'Unit 1 is in, with 1 finding. Tell whoever started you that unit 1 is in, and ' + 'stop.\n',
    );
  });

  test('refuses an answer before every doc was read and names the commands left', async (t) => {
    const c = await SubmitCase.make(t);
    await c.readDocs(1, 1);

    const result = await c.submit(1, [deviation()]);

    exits(result, 1);
    assert.equal(result.stdout, '');
    includes(
      result.stderr,
      `Not taken: you didn't read docs/git.md through \`${c.command('doc', '1', '2')}\`. Read it, ` +
        'check the diff against it, update your answer, then submit it again with ' +
        `\`${c.command('submit', '1')}\`.`,
    );
    assert.ok(!fs.existsSync(path.join(c.runDir, 'accepted', 'unit-1.json')));
  });

  test('takes the uncovered finders answer without any doc read', async (t) => {
    const c = await SubmitCase.make(t);
    const result = await c.submit(3, []);

    exits(result, 0);
    assert.equal(
      result.stdout,
      "The uncovered finder's answer is in, with 0 findings. Tell whoever started you " +
        "that the uncovered finder's answer is in, and stop.\n",
    );
  });

  test('refuses an answer that breaks the schema and names where', async (t) => {
    const c = await SubmitCase.make(t);
    const { take: _, ...broken } = { ...deviation(), kind: 'nit' };
    broken.spots[0]!.line = '12';
    await c.readDocs(1, 2);

    const result = await c.submit(1, [broken]);

    exits(result, 1);
    includes(
      result.stderr,
      'Not taken: your answer breaks the schema:\n' +
        '  findings[0] needs take\n' +
        '  findings[0].kind must be one of "deviation", "conflict", "uncovered choice"\n' +
        '  findings[0].spots[0].line must be an integer\n' +
        `Fix it, then submit it again with \`${c.command('submit', '1')}\`.`,
    );
  });

  test('refuses spots that name no line at the head and keeps the answer it took', async (t) => {
    const c = await SubmitCase.make(t);
    await c.readDocs(1, 2);
    exits(await c.submit(1, [deviation('Taken')]), 0);
    const accepted = path.join(c.runDir, 'accepted', 'unit-1.json');
    const before = fs.readFileSync(accepted, 'utf8');
    const broken = deviation('Broken');
    broken.spots = [
      { path: 'src/gone.py', line: 1, follows: false },
      { path: 'tests/test_app.py', line: 0, follows: false },
      { path: 'tests/test_app.py', line: -3, follows: false },
      { path: 'tests/test_app.py', line: 2, follows: false },
    ];

    const result = await c.submit(1, [deviation('Fine'), broken]);

    exits(result, 1);
    assert.equal(
      result.stderr,
      "Not taken: your answer names evidence that isn't there:\n" +
        "  findings[1].spots[0]: src/gone.py isn't a file at the head\n" +
        '  findings[1].spots[1]: lines count from 1, so there is no line 0\n' +
        '  findings[1].spots[2]: lines count from 1, so there is no line -3\n' +
        '  findings[1].spots[3]: tests/test_app.py has 1 line at the head, so there is no line 2\n' +
        `Fix it, then submit it again with \`${c.command('submit', '1')}\`.\n`,
    );
    assert.equal(fs.readFileSync(accepted, 'utf8'), before);
  });

  test('refuses a rule from a file that isnt in the checkout', async (t) => {
    const c = await SubmitCase.make(t);
    await c.readDocs(1, 2);
    const broken = deviation();
    broken.rules = [
      { file: 'docs/missing.md', quote: 'Test behavior.', routed: true },
      { file: '../outside.md', quote: 'Test behavior.', routed: true },
      { file: 'docs', quote: 'Test behavior.', routed: true },
    ];

    const result = await c.submit(1, [broken]);

    exits(result, 1);
    includes(
      result.stderr,
      "  findings[0].rules[0]: docs/missing.md isn't a file in the checkout\n" +
        "  findings[0].rules[1]: ../outside.md isn't a file in the checkout\n" +
        "  findings[0].rules[2]: docs isn't a file in the checkout\n",
    );
    assert.ok(!fs.existsSync(path.join(c.runDir, 'accepted', 'unit-1.json')));
  });

  test('takes a spot outside the diff and a rule from a doc outside the unit', async (t) => {
    const c = await SubmitCase.make(t);
    await c.readDocs(1, 2);
    const found = deviation('Outside', 'AGENTS.md', 1);
    found.rules = [{ file: 'docs/prose.md', quote: 'Short sentences.', routed: false }];

    exits(await c.submit(1, [found]), 0);
  });

  test('refuses an answer with a key the schema doesnt have', async (t) => {
    const c = await SubmitCase.make(t);
    const extra = { ...deviation(), severity: 'high' };
    await c.readDocs(1, 2);

    const result = await c.submit(1, [extra]);

    exits(result, 1);
    includes(result.stderr, '  findings[0] has severity, which the schema has no place for\n');
  });

  test('refuses an answer that isnt json', async (t) => {
    const c = await SubmitCase.make(t);
    await c.readDocs(1, 2);

    const result = await c.submit(1, '{"findings": [');

    exits(result, 1);
    includes(result.stderr, "Not taken: your answer isn't JSON");
  });

  test('refuses a submit before the answer is written and says where it goes', async (t) => {
    const c = await SubmitCase.make(t);
    await c.readDocs(1, 2);

    const result = await c.step('submit', '1');

    exits(result, 1);
    includes(
      result.stderr,
      `Not taken: there is no answer at ${c.answerPath('unit-1.json')}. Write it there as JSON, ` +
        `with your tool for writing files, then submit it again with \`${c.command('submit', '1')}\`.`,
    );
  });
});
