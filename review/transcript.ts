#!/usr/bin/env node
/**
 * Print what the review agent did, from the transcript claude-code-action saves: each tool call with its input, on one
 * line. A tool's result can hold file contents or anything the agent read, so it shows only whether it was an error.
 * Secrets are redacted throughout.
 */
import fs from 'node:fs';

import { parse } from '../src/argparse.ts';
import { dumps } from '../src/pyjson.ts';
import { SECRETS } from './sanitize.ts';

const WIDTH = 300;

/** The text on one line after the indent, redacted, and cut to WIDTH characters. */
function line(indent: string, text: string): string {
  const characters = [...(indent + text.split(/\s+/).filter(Boolean).join(' ').replace(SECRETS, '[redacted]'))];
  return characters.length <= WIDTH ? characters.join('') : `${characters.slice(0, WIDTH - 1).join('')}…`;
}

interface Part {
  readonly type: string;
  readonly name?: string;
  readonly input?: unknown;
  readonly is_error?: boolean;
}

const args = parse(
  {
    prog: 'transcript.ts',
    help: '',
    options: [
      {
        flag: '--file',
        dest: 'file',
        metavar: 'FILE',
        required: true,
        help: "claude-code-action's " + 'claude-execution-output.json',
      },
    ],
  },
  process.argv.slice(2),
);
const messages: { type?: string; parent_tool_use_id?: string; message: { content: (Part | string)[] } }[] = JSON.parse(
  fs.readFileSync(String(args.file), 'utf8'),
);
for (const message of messages) {
  if (message.type !== 'assistant' && message.type !== 'user') continue;
  const indent = message.parent_tool_use_id ? '  [subagent] ' : '';
  for (const part of message.message.content) {
    if (typeof part === 'string') continue;
    if (part.type === 'tool_use') process.stdout.write(`${line(indent, `${part.name} ${dumps(part.input)}`)}\n`);
    else if (part.type === 'tool_result' && part.is_error) process.stdout.write(`${indent}  -> error\n`);
  }
}
