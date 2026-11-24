#!/usr/bin/env node
/**
 * The change a review reads, from the merge base of a base commit to a head commit, as fixed git commands. Nothing a
 * caller passes reaches git as an option, so the wizard can hand it a path or a page as an agent typed them. Run as a
 * script, `shown` prints the head lines each diff shows, for the report to pick where each new thread opens.
 */
import { spawnSync } from 'node:child_process';

import { parse } from '../src/argparse.ts';
import { runAsScript } from '../src/main.ts';
import { repr, splitlines } from '../src/pystr.ts';

// How many lines a tool returns at most, so one call can't fill the agent's context.
const LINES = 1000;
const HUNK = /^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@/;

/** A call the wizard won't run, with the reason for the agent. */
export class Refused extends Error {}

/** What git printed. Every argument is fixed here or already checked, so none is the agent's text as an option. */
export function git(...args: string[]): string {
  return gitWithEnv({}, ...args);
}

/** What git printed, run with env added to this process's environment, such as GIT_INDEX_FILE. */
export function gitWithEnv(env: Readonly<Record<string, string>>, ...args: string[]): string {
  const run = spawnSync('git', ['--literal-pathspecs', ...args], {
    env: { ...process.env, ...env },
    maxBuffer: Infinity,
  });
  if (run.status !== 0) throw new Refused(`git said: ${String(run.stderr ?? run.error).trim()}`);
  return run.stdout.toString('utf8');
}

/** The hash of the commit rev names. --end-of-options, and the ^{commit} after rev, keep rev from being read as an option. */
export function commit(rev: string): string {
  return git('rev-parse', '--verify', '--end-of-options', `${rev}^{commit}`).trim();
}

/** The change from the merge base of a base commit to a head commit, which every tool reads from. */
export class Change {
  readonly base: string;
  readonly head: string;
  readonly range: string;
  readonly start: string;

  constructor(base: string, head: string) {
    this.base = commit(base);
    this.head = commit(head);
    this.range = `${this.base}...${this.head}`;
    this.start = git('merge-base', this.base, this.head).trim();
  }

  paths(): string[] {
    return git('diff', '--name-only', '-z', '--no-renames', this.range).split('\0').filter(Boolean);
  }

  raw(path: string): string[] {
    return splitlines(git('diff', '--no-ext-diff', '--no-textconv', '--no-renames', this.range, '--', path));
  }

  /** The head lines each path's diff shows, which a review comment can be left on. */
  shown(): Record<string, number[]> {
    return Object.fromEntries(
      this.paths().map((path) => [path, marked(this.raw(path)).flatMap(([n]) => (typeof n === 'number' ? [n] : []))]),
    );
  }

  /** The path's diff, each line numbered as numbered() says. */
  lines(path: string): string[] {
    return numbered(this.raw(path));
  }

  changed(): string {
    return this.paths()
      .map((path) => `${this.lines(path).length}\t${path}\n`)
      .join('');
  }

  log(page = 1): string {
    return paged(
      'the log',
      splitlines(git('log', '--no-decorate', '--format=medium', `${this.start}..${this.head}`)),
      page,
    );
  }

  diff(path: string, page = 1): string {
    if (!this.paths().includes(checked(path))) throw new Refused(`${path} isn't one of the paths the change touches.`);
    return paged(path, this.lines(path), page);
  }
}

/** How many pages a tool's output of count lines takes. */
function pages(count: number): number {
  return Math.max(Math.ceil(count / LINES), 1);
}

/** One page of the lines, with a line after it that says where it is when there's more than one. */
function paged(name: string, lines: readonly string[], page: number): string {
  const count = pages(lines.length);
  if (page > count) throw new Refused(`${name} has ${count} pages.`);
  const text = lines
    .slice((page - 1) * LINES, page * LINES)
    .map((line) => `${line}\n`)
    .join('');
  if (count === 1) return text;
  const more = page < count ? `: run it again with page ${page + 1} for more` : '';
  return `${text}(page ${page} of ${count}${more})\n`;
}

/** The path, once it's a path from the repo root that doesn't climb out of it. */
function checked(path: string): string {
  if (!path || path.startsWith('/') || path.split('/').includes('..')) {
    throw new Refused(`${repr(path)} must be a path from the repo root, without "..".`);
  }
  return path;
}

/**
 * Each line of a diff with the head's line number for it: a number for a line in a hunk that the head has, '' for
 * another line in a hunk, and null for a header or hunk line.
 */
function marked(diff: readonly string[]): [number | '' | null, string][] {
  const marks: [number | '' | null, string][] = [];
  let number: number | null = null;
  for (const line of diff) {
    const found = HUNK.exec(line);
    const first = line.slice(0, 1);
    if (found) {
      number = Number(found[1]);
      marks.push([null, line]);
    } else if (![' ', '+', '-', '\\'].includes(first)) {
      // Every line in a hunk starts with one of those, so this one starts the next file's header.
      number = null;
      marks.push([null, line]);
    } else if (number === null) {
      marks.push([null, line]);
    } else if (first === ' ' || first === '+') {
      marks.push([number, line]);
      number += 1;
    } else {
      marks.push(['', line]);
    }
  }
  return marks;
}

/**
 * A diff's lines, with each line in a hunk that the head has led by its line number there, and every other line in a
 * hunk led by blanks, so the agent copies a line number instead of counting. The header and hunk lines stay as git
 * wrote them.
 */
function numbered(diff: readonly string[]): string[] {
  const marks = marked(diff);
  const width = Math.max(0, ...marks.flatMap(([n]) => (n ? [String(n).length] : [])));
  return marks.map(([n, line]) => (n === null ? line : `${String(n).padStart(width)} ${line}`));
}

function main(): void {
  const args = parse(
    {
      prog: 'change.ts',
      help: '',
      commandRequired: true,
      options: [
        {
          flag: '--base',
          dest: 'base',
          metavar: 'BASE',
          required: true,
          help: 'the commit the reviewed change starts from',
        },
        { flag: '--head', dest: 'head', metavar: 'HEAD', required: true, help: 'the commit that is reviewed' },
      ],
      commands: { shown: { help: 'print as JSON the head lines each diff shows' } },
    },
    process.argv.slice(2),
  );
  process.stdout.write(`${JSON.stringify(new Change(String(args.base), String(args.head)).shown())}\n`);
}

if (runAsScript(import.meta.filename)) main();
