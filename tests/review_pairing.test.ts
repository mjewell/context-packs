import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { describe, test } from 'node:test';

import { excludes, exits, includes } from './expect.ts';
import { F1, F3, finding, PairingCase } from './pairing_case.ts';

interface Finding {
  readonly headline: string;
  readonly take: string;
  readonly spots: readonly { readonly path: string; readonly line: number }[];
}

/**
 * A pack-review thread as threads.ts prints it: its first comment's text is GitHub's bodyText of the comment that
 * opened it, which says what the finding is.
 */
function opened(id: string, found: Finding, replies: readonly unknown[] = [], resolved = false) {
  const first = {
    id: `${id}_c`,
    author: 'github-actions',
    at: '2026-11-01T10:00:00Z',
    text: `pack-review found a deviation here at abc1234: ${found.headline}\n${found.take}`,
    ours: true,
  };
  return { id, path: found.spots[0]!.path, line: found.spots[0]!.line, resolved, comments: [first, ...replies] };
}

const ALICE = {
  id: 'RC_2',
  author: 'alice',
  at: '2026-11-02T10:00:00Z',
  text: 'Kept on purpose: the balance spec.',
  ours: false,
};

/**
 * The pairing agent gets this run's findings and the findings pack-review's threads were opened for, and no comment
 * anyone wrote, so no comment can bias which thread a finding lands in.
 */
describe('PromptTests', () => {
  test('gives the new findings and each threads opening comment and no reply', async (t) => {
    const c = await PairingCase.make(t);
    c.given([F1, F3], [opened('T_1', finding('A magic number in the sim'), [ALICE])]);

    const outputs = await c.prompt();

    assert.equal(outputs.needed, 'true');
    const prompt = outputs.prompt!;
    includes(prompt, 'A game number in sim code');
    includes(prompt, 'A second RNG');
    includes(
      prompt,
      '"T_1" on src/sim.ts:42: "pack-review found a deviation here at abc1234: A magic number in the ' + 'sim',
    );
    excludes(prompt, 'balance spec');
    excludes(prompt, 'alice');
  });

  test('runs the agent with only the tool that returns its answer and the pairs schema', async (t) => {
    const c = await PairingCase.make(t);
    c.given([F1], [opened('T_1', F1)]);

    const args = (await c.prompt())['claude-args']!;

    // Claude Code returns an answer to --json-schema through the StructuredOutput tool, which --tools '' removes.
    includes(args, '--tools StructuredOutput');
    includes(args, '--strict-mcp-config');
    includes(args, '"pairs"');
  });

  test('needs no agent when there are no threads or no findings', async (t) => {
    const c = await PairingCase.make(t);
    for (const [findings, threads] of [
      [[F1], []],
      [[], [opened('T_1', F1)]],
    ] as const) {
      fs.writeFileSync(c.output, '');
      c.given(findings, threads);

      assert.equal((await c.prompt()).needed, 'false', `${findings.length} findings, ${threads.length} threads`);
    }
  });
});

/** Two findings, and a thread for each, the second resolved. */
class CheckCase extends PairingCase {
  protected override setUp(): void {
    super.setUp();
    this.given([F1, F3], [opened('T_1', F1), opened('T_2', F3, [], true)]);
  }
}

/** The post job gets only pairs that name a new finding and one of pack-review's threads, each at most once. */
describe('CheckTests', () => {
  test('writes the pairs for the post job', async (t) => {
    const c = await CheckCase.make(t);
    const run = await c.check([{ finding: 0, thread: 'T_1' }]);

    exits(run, 0);
    assert.deepEqual(c.matched(), { pairs: [{ finding: 0, thread: 'T_1' }] });
  });

  test('writes no pairs when the agent didnt run', async (t) => {
    const c = await CheckCase.make(t);
    assert.equal((await c.check()).status, 0);
    assert.deepEqual(c.matched(), { pairs: [] });
  });

  test('refuses pairs that name no finding or another thread or repeat one', async (t) => {
    const c = await CheckCase.make(t);
    for (const [pairs, says] of [
      [[{ finding: 2, thread: 'T_1' }], 'finding 2'],
      [[{ finding: 0, thread: 'T_9' }], 'T_9'],
      [
        [
          { finding: 0, thread: 'T_1' },
          { finding: 0, thread: 'T_2' },
        ],
        'finding 0',
      ],
      [
        [
          { finding: 0, thread: 'T_1' },
          { finding: 1, thread: 'T_1' },
        ],
        'T_1',
      ],
    ] as const) {
      const run = await c.check(pairs);

      assert.equal(run.status, 1, JSON.stringify(pairs));
      includes(run.stderr, says, JSON.stringify(pairs));
      assert.ok(!fs.existsSync(path.join(c.root, 'paired.json')), JSON.stringify(pairs));
    }
  });

  test('refuses an answer that isnt pairs', async (t) => {
    const c = await CheckCase.make(t);
    const run = await c.check('');

    exits(run, 1);
    includes(run.stderr, 'no pairs');
  });
});

const BOB = { id: 'RC_3', hidden: 'author lacks write access' };
const RELAYED = {
  id: 'RC_4',
  author: 'github-actions',
  at: '2026-11-03T10:00:00Z',
  text: '🤖 abc1234\n\nAlice says this is deliberate.',
  ours: true,
};
const LATER = { id: 'RC_5', author: 'alice', at: '2026-11-04T10:00:00Z', text: 'Fixed in the last push.', ours: false };

/** The pairing job once the pairs are checked: F1 continues T1. The review ran again at the head. */
class CommentCase extends PairingCase {
  protected override setUp(): void {
    super.setUp();
    this.thread([ALICE, BOB]);
    fs.writeFileSync(path.join(this.root, 'paired.json'), JSON.stringify({ pairs: [{ finding: 0, thread: 'T_1' }] }));
  }

  thread(replies: readonly unknown[]): void {
    this.given([F1, F3], [opened('T_1', F1, replies), opened('T_2', finding('Old'), [], true)], 'e'.repeat(40));
  }

  async commentPrompt(): Promise<Record<string, string>> {
    const run = await this.script(
      'pairing',
      'comment-prompt',
      '--report',
      'report.json',
      '--threads',
      'threads.json',
      '--paired',
      'paired.json',
    );
    assert.equal(run.status, 0, run.stderr);
    return this.outputs();
  }

  commentCheck(commentary?: string | readonly unknown[]) {
    let args: string[] = [];
    if (commentary !== undefined) {
      fs.writeFileSync(
        path.join(this.root, 'commentary.json'),
        typeof commentary === 'string' ? commentary : JSON.stringify({ commentary }),
      );
      args = ['--commentary', 'commentary.json'];
    }
    return this.script('pairing', 'comment-check', '--paired', 'paired.json', ...args);
  }
}

/**
 * The commentary agent gets every paired finding with its thread, told which comments are its own and which replies
 * came after its last one, so it can tell what it already said.
 */
describe('CommentPromptTests', () => {
  test('gives each paired finding with its threads replies and the commit it was found at', async (t) => {
    const c = await CommentCase.make(t);
    const prompt = (await c.commentPrompt()).prompt!;

    includes(prompt, 'A game number in sim code');
    includes(prompt, `ran again at ${'e'.repeat(7)} and still finds each finding`);
    includes(prompt, 'author lacks write access');
    excludes(prompt, 'A second RNG');
    excludes(prompt, 'Old');
  });

  test('marks its own comments as its own', async (t) => {
    const c = await CommentCase.make(t);
    c.thread([ALICE, RELAYED]);

    const prompt = (await c.commentPrompt()).prompt!;

    includes(prompt, '- you (pack-review), opening the thread: "pack-review found a deviation');
    includes(prompt, '- you (pack-review), at 2026-11-03T10:00:00Z: "🤖 abc1234');
    excludes(prompt, 'github-actions');
  });

  test('marks the replies after its last comment as new', async (t) => {
    const c = await CommentCase.make(t);
    c.thread([ALICE, RELAYED, LATER]);

    const prompt = (await c.commentPrompt()).prompt!;

    includes(prompt, '- alice at 2026-11-02T10:00:00Z: "Kept on purpose: the balance spec."');
    includes(prompt, '- alice at 2026-11-04T10:00:00Z, new since your last comment: "Fixed in the last push."');
  });

  test('says why a comment was minimized', async (t) => {
    const c = await CommentCase.make(t);
    c.thread([
      { ...ALICE, minimized: 'outdated' },
      { ...RELAYED, minimized: 'resolved' },
    ]);

    const prompt = (await c.commentPrompt()).prompt!;

    includes(prompt, '- alice at 2026-11-02T10:00:00Z, minimized as outdated: "Kept on purpose');
    includes(prompt, '- you (pack-review), at 2026-11-03T10:00:00Z, minimized as resolved: "🤖 abc1234');
  });

  test('asks about a paired thread even with no new reply', async (t) => {
    const c = await CommentCase.make(t);
    c.thread([ALICE, RELAYED]);

    assert.equal((await c.commentPrompt()).needed, 'true');
  });

  test('runs the agent with only the tool that returns its answer and the commentary schema', async (t) => {
    const c = await CommentCase.make(t);
    const args = (await c.commentPrompt())['claude-args']!;

    includes(args, '--tools StructuredOutput');
    includes(args, '"commentary"');
  });

  test('needs no agent when nothing is paired', async (t) => {
    const c = await CommentCase.make(t);
    fs.writeFileSync(path.join(c.root, 'paired.json'), JSON.stringify({ pairs: [] }));

    assert.equal((await c.commentPrompt()).needed, 'false');
  });
});

/** The post job gets commentary only on paired findings, one each, cleaned like the findings. */
describe('CommentCheckTests', () => {
  test('adds the commentary to the pairs', async (t) => {
    const c = await CommentCase.make(t);
    const run = await c.commentCheck([{ finding: 0, text: `Alice says it​ is deliberate. ghp_${'a'.repeat(36)}` }]);

    exits(run, 0);
    assert.deepEqual(c.matched(), {
      pairs: [{ finding: 0, thread: 'T_1' }],
      commentary: [{ finding: 0, text: 'Alice says it is deliberate. ' + '[redacted]' }],
    });
  });

  test('adds no commentary when the agent didnt run or had nothing to say', async (t) => {
    const c = await CommentCase.make(t);
    for (const commentary of [undefined, []]) {
      fs.writeFileSync(path.join(c.root, 'paired.json'), JSON.stringify({ pairs: [{ finding: 0, thread: 'T_1' }] }));

      assert.equal((await c.commentCheck(commentary)).status, 0, `${commentary}`);
      assert.deepEqual(c.matched().commentary, [], `${commentary}`);
    }
  });

  test('refuses commentary on an unpaired finding twice on one or empty', async (t) => {
    const c = await CommentCase.make(t);
    for (const [commentary, says] of [
      [[{ finding: 1, text: 'Hi.' }], 'finding 1'],
      [
        [
          { finding: 0, text: 'A.' },
          { finding: 0, text: 'B.' },
        ],
        'finding 0',
      ],
      [[{ finding: 0, text: ' ​ ' }], 'empty'],
    ] as const) {
      const run = await c.commentCheck(commentary);

      assert.equal(run.status, 1, JSON.stringify(commentary));
      includes(run.stderr, says);
      assert.ok(!('commentary' in c.matched()));
    }
  });

  test('refuses an answer that isnt commentary', async (t) => {
    const c = await CommentCase.make(t);
    const run = await c.commentCheck('{}');

    exits(run, 1);
    includes(run.stderr, 'no commentary');
  });
});
