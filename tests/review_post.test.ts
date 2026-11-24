import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { describe, test } from 'node:test';

import { excludes, exits, includes } from './expect.ts';
import { connection, ok, pullRequest, role } from './fake_github.ts';
import { F1, F3 } from './pairing_case.ts';
import { BASE, HEAD, MARKER, ours, ReviewCase, reviewThread } from './review_case.ts';

interface Input {
  readonly [key: string]: unknown;
}

/** The post job: the find job's report, the pairing job's pairs and commentary, and the PR on the fake GitHub. */
class PostCase extends ReviewCase {
  protected override async setUp(): Promise<void> {
    await super.setUp();
    Object.assign(this.github.responses, {
      PullRequest: pullRequest(),
      Threads: ok({ repository: { pullRequest: { reviewThreads: connection([]) } } }),
      AddReview: ok({ addPullRequestReview: { pullRequestReview: { id: 'PRR_1' } } }),
      AddReply: ok({ addPullRequestReviewThreadReply: { comment: { id: 'RC_9' } } }),
      AddComment: ok({}),
    });
    this.github.rest['/repos/o/r/collaborators/alice/permission'] = role('write');
  }

  threads(...threads: unknown[]): void {
    this.github.responses.Threads = ok({ repository: { pullRequest: { reviewThreads: connection(threads) } } });
  }

  post(
    findings: readonly unknown[],
    anchors: readonly unknown[],
    pairs: readonly unknown[] = [],
    commentary: readonly unknown[] = [],
  ) {
    fs.writeFileSync(
      path.join(this.root, 'report.json'),
      JSON.stringify({ base: BASE, base_ref: 'main', head: HEAD, findings, anchors }),
    );
    fs.writeFileSync(path.join(this.root, 'paired.json'), JSON.stringify({ pairs, commentary }));
    return this.script('post', '--pr', 7, '--report', 'report.json', '--paired', 'paired.json');
  }

  /**
   * What the post wrote in threads: the review that opened the new threads, or null when there were none, and the
   * replies by thread. No review is ever left pending: the new threads are submitted as they're created, and each
   * reply is posted on its own.
   */
  review(): [Input | null, Record<string, Input>] {
    assert.deepEqual(this.sent('SubmitReview'), []);
    const added = this.sent('AddReview').map((sent) => sent.input as Input);
    assert.ok(added.length <= 1);
    for (const review of added) assert.equal(review.event, 'COMMENT');
    const replies: Record<string, Input> = {};
    for (const sent of this.sent('AddReply')) {
      const input = sent.input as Input;
      replies[input.pullRequestReviewThreadId as string] = input;
    }
    for (const reply of Object.values(replies)) assert.ok(!('pullRequestReviewId' in reply));
    return [added[0] ?? null, replies];
  }

  /** The comment a thread opens with for F1 with these fields. */
  async opening(fields: Record<string, unknown>): Promise<string> {
    await this.post([{ ...F1, ...fields }], [{ path: 'src/sim.ts', line: 42 }]);
    return firstThread(this.review()[0]).body as string;
  }
}

function firstThread(added: Input | null): Input {
  return (added!.threads as Input[])[0]!;
}

/** A finding no thread was opened for gets a thread of its own, on the spot report.ts anchored it to. */
describe('a new finding', () => {
  test('opens a thread on each new findings anchor', async (t) => {
    const c = await PostCase.make(t);
    const result = await c.post(
      [F1, F3],
      [
        { path: 'src/sim.ts', line: 42 },
        { path: 'src/rng.ts', line: 17 },
      ],
    );

    exits(result, 0);
    const [added, replies] = c.review();
    assert.equal(added!.pullRequestId, 'PR_1');
    assert.equal(added!.commitOID, HEAD);
    assert.deepEqual(
      (added!.threads as Input[]).map((th) => [th.path, th.line, th.side]),
      [
        ['src/sim.ts', 42, 'RIGHT'],
        ['src/rng.ts', 17, 'RIGHT'],
      ],
    );
    assert.deepEqual(replies, {});
  });

  test('opens it with the finding written for people and for later runs to pair', async (t) => {
    const c = await PostCase.make(t);
    const found = { ...F1, rules: [{ file: 'AGENTS.md', quote: 'Game numbers live in content.', routed: true }] };

    await c.post([found], [{ path: 'src/sim.ts', line: 42 }]);

    assert.equal(
      firstThread(c.review()[0]).body,
      '🤖 `deviation` `hhhhhhh` **A game number in sim code**\n\n' +
        'From `AGENTS.md`:\n\n> Game numbers live in content.\n\n' +
        `Move it to content.\n\n${MARKER}`,
    );
  });

  test('says when a rules doc wasnt routed to the change', async (t) => {
    const c = await PostCase.make(t);
    const body = await c.opening({
      rules: [
        { file: 'AGENTS.md', quote: 'Keep it short.', routed: true },
        { file: 'docs/sim.md', quote: 'Game numbers live in content.', routed: false },
      ],
    });

    includes(
      body,
      'From `AGENTS.md`:\n\n> Keep it short.\n\n' +
        "From `docs/sim.md`, whose `when` didn't match this change:\n\n> Game numbers live in content.\n\n",
    );
  });

  test('lists the signs a deviation is deliberate before the take', async (t) => {
    const c = await PostCase.make(t);
    const body = await c.opening({
      deliberate: ['A comment at the spot: "Tuned by hand."', 'Commit abc1234 says so.'],
    });

    includes(
      body,
      'Signs it may be deliberate:\n\n- A comment at the spot: "Tuned by hand."\n' +
        '- Commit abc1234 says so.\n\nMove it to content.',
    );
  });

  test('shows how the code makes an uncovered choice now', async (t) => {
    const c = await PostCase.make(t);
    const body = await c.opening({
      kind: 'uncovered choice',
      exemplars: [
        { way: 'Loaded at startup', examples: ['src/load.ts:8', 'src/boot.ts:3'] },
        { way: 'Loaded on first use', examples: ['src/lazy.ts:12'] },
      ],
    });

    includes(
      body,
      'How the code does it now:\n\n- Loaded at startup: `src/load.ts:8`, `src/boot.ts:3`\n' +
        '- Loaded on first use: `src/lazy.ts:12`\n\nMove it to content.',
    );
  });

  test('names the other spots it was found at than the threads line', async (t) => {
    const c = await PostCase.make(t);
    const body = await c.opening({
      spots: [
        { path: 'src/sim.ts', line: 42, follows: false },
        { path: 'src/sim.ts', line: 7, follows: true },
        { path: 'src/rng.ts', line: 9, follows: false },
      ],
    });

    includes(body, 'Also found at `src/rng.ts:9`.\n\nMove it to content.');
  });

  test('names the spot it was found at when the thread opens on one that follows the rule', async (t) => {
    const c = await PostCase.make(t);
    const spots = [
      { path: 'src/sim.ts', line: 42, follows: true },
      { path: 'src/old.ts', line: 3, follows: false },
    ];
    await c.post([{ ...F1, spots }], [{ path: 'src/sim.ts', line: 42 }]);

    includes(firstThread(c.review()[0]).body as string, 'Also found at `src/old.ts:3`.');
  });

  test('keeps the findings text from notifying anyone or hiding text', async (t) => {
    const c = await PostCase.make(t);
    const found = { ...F1, headline: 'Ask @alice <!-- or not -->', take: 'See <b>this</b>.' };

    await c.post([found], [{ path: 'src/sim.ts', line: 42 }]);

    const body = firstThread(c.review()[0]).body as string;
    includes(body, '**Ask @\u2060alice &lt;!-- or not -->**');
    includes(body, 'See &lt;b>this&lt;/b>.');
    excludes(body, '```json');
  });

  test('opens no thread for a finding the diff doesnt show', async (t) => {
    const c = await PostCase.make(t);
    const result = await c.post([F1], [null]);

    exits(result, 0);
    assert.deepEqual(c.github.writes(), ['AddComment']);
  });
});

/** A finding that continues a thread is answered in it only when there's something to say. */
describe('a finding that continues a thread', () => {
  test('stays quiet on an open thread with nothing to add', async (t) => {
    const c = await PostCase.make(t);
    c.threads(reviewThread('T_1'));

    const result = await c.post([F1], [{ path: 'src/sim.ts', line: 42 }], [{ finding: 0, thread: 'T_1' }]);

    exits(result, 0);
    assert.deepEqual(c.github.writes(), ['AddComment']);
    includes(result.stdout, 'opened 0 threads, replied in 0');
  });

  test('tells a resolved thread its finding is still found', async (t) => {
    const c = await PostCase.make(t);
    c.threads(reviewThread('T_1', { resolved: true }));

    await c.post([F1], [null], [{ finding: 0, thread: 'T_1' }]);

    const [added, replies] = c.review();
    assert.equal(added, null);
    const body = replies.T_1!.body as string;
    assert.equal(body, `🤖 \`still found\` \`hhhhhhh\`\n\n${MARKER}`);
    assert.ok(body.endsWith(MARKER));
  });

  test('says still found once while the thread stays resolved', async (t) => {
    const c = await PostCase.make(t);
    c.threads(reviewThread('T_1', { resolved: true, replies: [ours('🤖 still found 1234567', { id: 'RC_8' })] }));

    const result = await c.post([F1], [null], [{ finding: 0, thread: 'T_1' }]);

    exits(result, 0);
    assert.deepEqual(c.github.writes(), ['AddComment']);
  });

  test('names the thread when github refuses a reply', async (t) => {
    const c = await PostCase.make(t);
    c.github.responses.AddReply = [200, { data: null, errors: [{ message: 'Thread is locked' }] }];
    c.threads(reviewThread('T_1', { resolved: true }));

    const result = await c.post([F1], [null], [{ finding: 0, thread: 'T_1' }]);

    exits(result, 1);
    includes(result.stderr, 'T_1');
    includes(result.stderr, 'Thread is locked');
  });

  test('stops on a pair with a thread that isnt pack reviews on this pr', async (t) => {
    const c = await PostCase.make(t);
    c.threads(reviewThread('T_1'));

    const result = await c.post([F1], [null], [{ finding: 0, thread: 'T_9' }]);

    exits(result, 1);
    includes(result.stderr, 'T_9');
    assert.deepEqual(c.github.writes(), []);
  });
});

describe('a PR that moved on', () => {
  test('posts nothing when the pr moved on or to another base', async (t) => {
    const c = await PostCase.make(t);
    for (const [answer, says] of [
      [pullRequest({ head: 'o'.repeat(40) }), 'moved on'],
      [pullRequest({ baseRef: 'release' }), 'moved from main'],
    ] as const) {
      c.github.responses.PullRequest = answer;

      const result = await c.post([F1], [{ path: 'src/sim.ts', line: 42 }]);

      assert.equal(result.status, 0, `${says}: ${result.stderr}`);
      includes(result.stdout, says);
      assert.deepEqual(c.github.writes(), [], says);
    }
  });
});

/** Every check that can fail runs before the first write, so a run that stops leaves the PR as it was. */
describe('checks before the first write', () => {
  test('writes nothing when the summary wont fit though each thread would', async (t) => {
    const c = await PostCase.make(t);
    const findings = [
      { ...F1, headline: 'x'.repeat(33000) },
      { ...F3, headline: 'y'.repeat(33000) },
    ];

    const result = await c.post(findings, [
      { path: 'src/sim.ts', line: 42 },
      { path: 'src/rng.ts', line: 17 },
    ]);

    exits(result, 1);
    includes(result.stderr, '65536');
    assert.deepEqual(c.github.writes(), []);
  });
});

/** Commentary on F1, which continues T_1, and the body of the reply the post wrote there. */
async function reply(c: PostCase, text: string, resolved = false): Promise<string> {
  c.threads(reviewThread('T_1', { resolved }));
  const result = await c.post([F1], [null], [{ finding: 0, thread: 'T_1' }], [{ finding: 0, text }]);
  exits(result, 0);
  return c.review()[1].T_1!.body as string;
}

/**
 * Commentary is posted in its finding's thread, open or resolved, as a quote that can't notify anyone or hide text.
 */
describe('commentary', () => {
  test('replies with the commentary on an open thread', async (t) => {
    const c = await PostCase.make(t);
    assert.equal(
      await reply(c, 'Alice says this is deliberate, per the balance spec.'),
      `🤖 \`hhhhhhh\`\n\n> Alice says this is deliberate, per the balance spec.\n\n${MARKER}`,
    );
  });

  test('keeps a mention from notifying anyone whatever markdown is around it', async (t) => {
    const c = await PostCase.make(t);
    const found = { ...F1, headline: 'Ask ` @alice ` or \\@bob', take: 'Or `@carol`.' };

    await c.post([found], [{ path: 'src/sim.ts', line: 42 }]);

    const body = firstThread(c.review()[0]).body as string;
    // GitHub links a mention only when a login's first character follows the @.
    assert.doesNotMatch(body, /@[A-Za-z0-9]/);
    includes(body, '**Ask ` @\u2060alice ` or \\@\u2060bob**');
  });

  test('says a resolved thread is still found before the commentary', async (t) => {
    const c = await PostCase.make(t);
    assert.equal(
      await reply(c, 'Alice said it was fixed in abc1234.', true),
      `🤖 \`still found\` \`hhhhhhh\`\n\n> Alice said it was fixed in abc1234.\n\n${MARKER}`,
    );
  });

  test('quotes every line', async (t) => {
    const c = await PostCase.make(t);
    includes(await reply(c, 'One.\n\nTwo.'), '> One.\n>\n> Two.\n');
  });

  test('keeps mentions from notifying and html from hiding text', async (t) => {
    const c = await PostCase.make(t);
    const body = await reply(c, '@alice and @org/team-a said so. <!-- hidden --> <b>x</b> Mail a@b.com.');

    includes(
      body,
      '> @\u2060alice and @\u2060org/team-a said so. &lt;!-- hidden --> &lt;b>x&lt;/b> Mail a@\u2060b.com.',
    );
  });
});
