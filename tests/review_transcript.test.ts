import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { describe, test } from 'node:test';

import { excludes, exits, includes } from './expect.ts';
import { ReviewCase } from './review_case.ts';

function call(id: string, name: string, input: unknown, parent: string | null = null) {
  return {
    type: 'assistant',
    parent_tool_use_id: parent,
    message: {
      content: [
        { type: 'text', text: 'Thinking out loud.' },
        { type: 'tool_use', id, name, input },
      ],
    },
  };
}

function result(id: string, text: string, { error = false, parent = null as string | null } = {}) {
  return {
    type: 'user',
    parent_tool_use_id: parent,
    message: {
      content: [{ type: 'tool_result', tool_use_id: id, is_error: error, content: [{ type: 'text', text }] }],
    },
  };
}

/** What a review run's log shows of what the agent did: each tool call, but never what a tool returned. */
class TranscriptCase extends ReviewCase {
  async show(messages: readonly unknown[]): Promise<string> {
    fs.writeFileSync(path.join(this.root, 'transcript.json'), JSON.stringify(messages));
    const run = await this.script('transcript', '--file', 'transcript.json');
    exits(run, 0);
    return run.stdout;
  }
}

describe('TranscriptTests', () => {
  test('lists each tool call with its input', async (t) => {
    const c = await TranscriptCase.make(t);
    const out = await c.show([
      { type: 'system', subtype: 'init' },
      call('t1', 'Read', { file_path: '/w/AGENTS.md' }),
      result('t1', 'the whole of AGENTS.md'),
      call('t2', 'Bash', { command: 'git diff b...h' }),
      result('t2', 'diff --git ...'),
      { type: 'result', subtype: 'success', num_turns: 3 },
    ]);

    assert.equal(out, 'Read {"file_path": "/w/AGENTS.md"}\nBash {"command": "git diff b...h"}\n');
  });

  test('marks the calls a subagent made', async (t) => {
    const c = await TranscriptCase.make(t);
    const out = await c.show([
      call('t1', 'Agent', { description: 'Check the core pack' }),
      call('s1', 'Read', { file_path: '/w/context-packs/gen/core/testing.md' }, 't1'),
      result('s1', 'testing doc', { parent: 't1' }),
      result('t1', 'ledger'),
    ]);

    assert.equal(
      out,
      'Agent {"description": "Check the core pack"}\n' +
        '  [subagent] Read {"file_path": "/w/context-packs/gen/core/testing.md"}\n',
    );
  });

  test('marks another tools error without showing what it returned', async (t) => {
    const c = await TranscriptCase.make(t);
    const out = await c.show([
      call('t1', 'Read', { file_path: '/etc/passwd' }),
      result('t1', 'root:x:0:0 and a secret', { error: true }),
    ]);

    assert.equal(out, 'Read {"file_path": "/etc/passwd"}\n  -> error\n');
    excludes(out, 'secret');
  });

  test('shortens a long input and keeps it on one line', async (t) => {
    const c = await TranscriptCase.make(t);
    const out = await c.show([call('t1', 'Agent', { prompt: `Read every doc.\n${'x'.repeat(500)}` })]);

    const lines = out.trimEnd().split('\n');
    assert.equal(lines.length, 1);
    assert.ok([...lines[0]!].length <= 300, lines[0]);
    assert.ok(lines[0]!.endsWith('…'), lines[0]);
  });

  test('redacts secrets in inputs', async (t) => {
    const c = await TranscriptCase.make(t);
    const token = `ghs_${'a'.repeat(36)}`;
    const out = await c.show([call('t1', 'Grep', { pattern: `Key ${token}` })]);

    excludes(out, token);
    includes(out, '[redacted]');
  });
});
