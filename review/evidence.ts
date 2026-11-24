/**
 * The checks on what a finder's answer cites that need no judgment: each spot is a line of a file at the head, and
 * each rule's file is in the checkout, where the finder read it. Whether a rule applies, or a spot breaks it, stays
 * with the agents.
 */
import fs from 'node:fs';
import path from 'node:path';

import { splitlines } from '../src/pystr.ts';
import { git } from './change.ts';

/** What a finding cites, as the findings schema shapes it. */
export interface Cited {
  readonly rules: readonly { readonly file: string }[];
  readonly spots: readonly { readonly path: string; readonly line: number }[];
}

/** The head's files, and how many lines one of them has, read once each. */
class Head {
  readonly #head: string;
  readonly #files: Set<string>;
  readonly #lines = new Map<string, number>();

  constructor(head: string) {
    this.#head = head;
    this.#files = new Set(git('ls-tree', '-r', '-z', '--name-only', head).split('\0').filter(Boolean));
  }

  has(file: string): boolean {
    return this.#files.has(file);
  }

  lines(file: string): number {
    if (!this.#lines.has(file)) this.#lines.set(file, splitlines(git('show', `${this.#head}:${file}`)).length);
    return this.#lines.get(file)!;
  }
}

/** Whether file names a file inside root, so a finder could have read it there. */
function inCheckout(root: string, file: string): boolean {
  const relative = path.relative(root, path.resolve(root, file));
  if (!relative || relative.startsWith('..') || path.isAbsolute(relative)) return false;
  return fs.statSync(path.join(root, relative), { throwIfNoEntry: false })?.isFile() ?? false;
}

/** What's wrong with the evidence the findings cite, one line each, naming where, as schema errors do. */
export function evidenceErrors(findings: readonly Cited[], head: string, root: string): string[] {
  const files = new Head(head);
  return findings.flatMap((finding, n) => [
    ...finding.spots.flatMap((spot, i) => {
      const where = `findings[${n}].spots[${i}]`;
      if (spot.line < 1) return [`${where}: lines count from 1, so there is no line ${spot.line}`];
      if (!files.has(spot.path)) return [`${where}: ${spot.path} isn't a file at the head`];
      const count = files.lines(spot.path);
      if (spot.line > count) {
        return [
          `${where}: ${spot.path} has ${count} line${count !== 1 ? 's' : ''} at the head, so there is no line ${spot.line}`,
        ];
      }
      return [];
    }),
    ...finding.rules.flatMap((rule, i) =>
      inCheckout(root, rule.file) ? [] : [`findings[${n}].rules[${i}]: ${rule.file} isn't a file in the checkout`],
    ),
  ]);
}
