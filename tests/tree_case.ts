/** A repo for the spec-tree skill's scripts to read trees from, and a tree to put in it. */
import fs from 'node:fs';
import path from 'node:path';
import type { TestContext } from 'node:test';

import { command, type Result, ROOT, run } from './scripts.ts';
import { tempDir } from './temp.ts';

export const TOOLS = path.join(ROOT, 'skills', 'spec-tree', 'scripts');

export const SMALL = `
    # Review {#review}

    A review checks a change against the repo's rules.

    - Finders check the diff {#finders}
      - Why: one finder per unit reads each file whole
    - The author decides each finding, see [[finders]]
    - A merge turns the finders' answers into one list of findings, writing one finding for each choice in the diff, however many rules from however many units flag that same choice at the same spots
    `;

/** text with the indent its lines share removed, and lines of only whitespace emptied. As Python's textwrap.dedent. */
export function dedent(text: string): string {
  const lines = text.split('\n').map((line) => (line.trim() ? line : ''));
  const indents = lines.filter(Boolean).map((line) => /^[ \t]*/.exec(line)![0]);
  const common = indents.reduce((a, b) => {
    let i = 0;
    while (i < a.length && a[i] === b[i]) i++;
    return a.slice(0, i);
  }, indents[0] ?? '');
  return lines.map((line) => line.slice(common.length)).join('\n');
}

/** A repo in a temporary folder, with spec trees written into it, and the trees CLI run from its root. */
export class TreeCase {
  readonly root: string;

  constructor(t: TestContext) {
    this.root = tempDir(t, 'context-packs-trees-');
    fs.mkdirSync(path.join(this.root, '.git'));
  }

  /** Writes text, dedented, without the blank lines it starts with. */
  write(file: string, text: string): void {
    const target = path.join(this.root, file);
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.writeFileSync(target, dedent(text).trimStart());
  }

  read(file: string): string {
    return fs.readFileSync(path.join(this.root, file), 'utf8');
  }

  trees(...args: string[]): Promise<Result> {
    return run([...command('skills/spec-tree/scripts/trees'), ...args], { cwd: this.root });
  }
}
