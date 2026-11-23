/** The context-packs block in AGENTS.md or CLAUDE.md, which the sync owns along with context-packs/gen/. */
import { createHash } from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';

import { GEN, ROOT } from './packs.ts';
import { byParts, exists, isDir, isFile, isSymlink, walk } from './paths.ts';
import { fail } from './stop.ts';

export const START = '<!-- context-packs:start -->\n';
const BLOCK = /^<!-- context-packs:start -->\n([\s\S]*?)^<!-- context-packs:end sha256:([0-9a-f]{12}) -->\n?/gm;
const MARKER = /^<!-- context-packs:start/m;
// A start marker holding a pack's name, as versions before one block per file wrote them.
const OLD_MARKER = /^<!-- context-packs:start (?!-->)/m;

/**
 * The block's header, saying where the tables' paths start from unless they're absolute, and where a doc's own paths
 * start: its folder first, then where its rows start.
 */
export function header(base: string): string {
  const outside = path.isAbsolute(base);
  return '## Context Packs\n\n'
    + 'Context packs bring shared rules and docs in from elsewhere. Each pack has its pack rules and a table of its '
    + 'pack docs here, and a doc may hold a table of its own. Before starting work that a row in any of these '
    + 'tables matches, read its doc. '
    + (outside ? '' : 'The paths in these tables start from the repo root. ')
    + "Look for a path a doc names in the doc's folder first, then from "
    + (outside ? 'the folder the session started in. ' : 'the repo root. ')
    + `The packs here, and everything under \`${GEN}/\`, are generated from \`${ROOT}/\`: `
    + 'change them there, never here.\n';
}

/** Where the instructions file's context-packs block sits, and its text. */
export interface Region {
  readonly text: string;
  readonly start: number;
  readonly end: number;
  readonly block: string;
}

function digest(body: string, docs: Buffer = Buffer.alloc(0)): string {
  return createHash('sha256').update(Buffer.from(body, 'utf8')).update(docs).digest('hex').slice(0, 12);
}

export function block(body: string, docs: Buffer = Buffer.alloc(0)): string {
  return `${START}${body}<!-- context-packs:end sha256:${digest(body, docs)} -->\n`;
}

/** The generated files' paths and contents, which the block's hash covers so edits to them are caught too. */
export function snapshot(folder: string): Buffer {
  if (!isDir(folder)) return Buffer.alloc(0);
  const files = walk(folder).filter(isFile).sort(byParts);
  return Buffer.concat(files.flatMap((file) => [
    Buffer.from(`${path.relative(folder, file)}\0`, 'utf8'), fs.readFileSync(file), Buffer.from('\0'),
  ]));
}

export function read(file: string): string {
  return fs.readFileSync(file).toString('utf8');
}

/**
 * The file the sync writes: whichever of AGENTS.md and CLAUDE.md holds the block, else a new AGENTS.md. Which
 * instruction file a repo uses is its call, so the sync stops for the block to be pasted into a file that exists, and
 * never writes through a symlink.
 */
export function instructions(repo: string): string {
  const [agentsMd, claudeMd] = [path.join(repo, 'AGENTS.md'), path.join(repo, 'CLAUDE.md')];
  const files = [agentsMd, claudeMd].filter((f) => isFile(f) && !isSymlink(f));
  for (const file of files) {
    // Checked first, since the block can't be found in a file with CRLF line endings.
    if (read(file).includes('\r')) fail(`context-packs: ${file} has CRLF line endings. Convert it to LF, then sync again.`);
  }
  const marked = files.filter((f) => MARKER.test(read(f)));
  if (marked.length > 1) {
    fail(`context-packs: ${agentsMd} and ${claudeMd} both have a context-packs block. `
         + "Delete it from the one that shouldn't be synced, then sync again.");
  }
  if (marked.length) return marked[0]!;
  const lines = block('');
  if (files.length > 1) {
    fail(`context-packs: Neither ${agentsMd} nor ${claudeMd} has a context-packs block. Add these two lines `
         + `to the one that should hold the packs, where the shared rules should go, then sync again:\n\n${lines}`);
  }
  if (files.length) {
    fail(`context-packs: ${files[0]} has no context-packs block. `
         + `Add these two lines where the shared rules should go, then sync again:\n\n${lines}`);
  }
  if (isSymlink(agentsMd)) {
    fail(`context-packs: ${agentsMd} is a symlink, and the sync would write through it. `
         + 'Delete it, then sync again to get a real file.');
  }
  if (isSymlink(claudeMd) && fs.readlinkSync(claudeMd) !== 'AGENTS.md') {
    fail(`context-packs: ${claudeMd} is a symlink, and the sync won't write through it. `
         + 'Replace it with the file it points to, or delete it, then sync again.');
  }
  return agentsMd;
}

/**
 * file's context-packs block, or a new file's empty one, after checking that nothing in it or in context-packs/gen/
 * was edited since the last sync.
 */
export function region(repo: string, file: string): Region {
  const text = exists(file) ? read(file) : block('');
  if (OLD_MARKER.test(text)) {
    fail(`context-packs: ${file} has context-packs blocks from an older version, which kept packs in `
         + 'docs/agents/. Replace everything from their first start marker to their last end marker with the two '
         + `lines below. Move each import pack in docs/agents/, such as docs/agents/core/, to ${ROOT}/, `
         + `delete docs/agents/generated/, and move your own docs into ${ROOT}/ or \`add\` their folder. `
         + `Then sync again:\n\n${block('')}`);
  }
  const blocks = [...text.matchAll(BLOCK)];
  if (blocks.length > 1) {
    fail(`context-packs: ${file} has more than one context-packs block. Delete all but one, then sync again.`);
  }
  const match = blocks[0];
  if (!match) {
    fail(`context-packs: ${file} has a context-packs start marker without its end marker. Replace it with `
         + `these two lines, then sync again:\n\n${block('')}`);
  }
  const [whole, body, sha] = match as unknown as [string, string, string];
  if (digest(body, snapshot(path.join(repo, GEN))) !== sha) {
    fail(`context-packs: ${file}: the context-packs block or a file in ${GEN} was edited since the `
         + `last sync. Move the change into ${ROOT}/ or outside the block, or revert it, then sync `
         + 'again.');
  }
  return { text, start: match.index, end: match.index + whole.length, block: whole };
}
