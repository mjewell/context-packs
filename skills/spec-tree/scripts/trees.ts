#!/usr/bin/env node
/**
 * Tools for spec trees, as the spec beside this folder, ../spec.md, defines them.
 *
 * Usage:
 *   node scripts/trees.ts check
 *   node scripts/trees.ts stats
 *   node scripts/trees.ts links-to <id>
 *   node scripts/trees.ts render <id>.tree.md [-o out.html]
 *
 * Node's standard library only, since the skill's folder is all an installed skill holds.
 */
import fs from 'node:fs';
import path from 'node:path';
import { parseArgs } from 'node:util';

import { check, linksTo, stats } from './tree_check.ts';
import { parse } from './tree_model.ts';
import { page, Stop } from './tree_render.ts';

const USAGE = 'usage: trees.ts {check,stats,links-to,render} ...';

function fail(message: string): never {
  throw new Stop(message);
}

/** The nearest folder at or above folder holding `.git`, which is a file in a worktree and a folder otherwise. */
function repoRoot(folder: string): string {
  for (let at = folder; ; at = path.dirname(at)) {
    if (fs.existsSync(path.join(at, '.git'))) return at;
    if (at === path.dirname(at)) fail(`trees.ts: ${folder} is not in a git repo`);
  }
}

/** Prints each problem in the repo's trees, and exits 1 when any fails. */
function runCheck(): void {
  const repo = repoRoot(process.cwd());
  const problems = check(repo);
  for (const [file, level, message] of problems)
    process.stdout.write(`${path.relative(repo, file)}: ${level}: ${message}\n`);
  process.exitCode = problems.some(([, level]) => level === 'fail') ? 1 : 0;
}

function runStats(): void {
  process.stdout.write(`${stats(repoRoot(process.cwd())).join('\n')}\n`);
}

function runLinksTo(id: string): void {
  const repo = repoRoot(process.cwd());
  const links = linksTo(repo, id);
  if (links === null) fail(`trees.ts: no node has the ID ${id}`);
  for (const [file, text] of links) process.stdout.write(`${path.relative(repo, file)}: ${text}\n`);
}

/** Writes the page beside the tree's file, as <id>.tree.html, unless the tree doesn't read as a tree. */
function render(tree: string, out: string | undefined): void {
  const file = fs.realpathSync(path.resolve(tree));
  const root = parse(file);
  if (root.problems.length) fail(root.problems.map(([at, message]) => `trees.ts: ${at}: ${message}`).join('\n'));
  const target = out ?? file.replace(/\.md$/, '.html');
  fs.writeFileSync(target, page(root, path.relative(repoRoot(path.dirname(file)), file)), 'utf8');
  process.stdout.write(`${target}\n`);
}

function usage(message: string): never {
  process.stderr.write(`${USAGE}\ntrees.ts: error: ${message}\n`);
  process.exit(2);
}

function main(argv: readonly string[]): void {
  const [command, ...rest] = argv;
  let parsed;
  try {
    parsed = parseArgs({ args: [...rest], allowPositionals: true, options: { out: { type: 'string', short: 'o' } } });
  } catch (error) {
    usage((error as Error).message);
  }
  const { positionals, values } = parsed;
  const expected: Record<string, number> = { check: 0, stats: 0, 'links-to': 1, render: 1 };
  if (command === undefined) usage('the following arguments are required: command');
  if (!(command in expected)) usage(`argument command: invalid choice: '${command}'`);
  if (positionals.length < expected[command]!)
    usage(`the following arguments are required: ${command === 'render' ? 'tree' : 'id'}`);
  if (positionals.length > expected[command]! || (values.out !== undefined && command !== 'render')) {
    usage(`unrecognized arguments: ${rest.join(' ')}`);
  }
  if (command === 'check') runCheck();
  else if (command === 'stats') runStats();
  else if (command === 'links-to') runLinksTo(positionals[0]!);
  else render(positionals[0]!, values.out);
}

try {
  main(process.argv.slice(2));
} catch (error) {
  if (!(error instanceof Stop)) throw error;
  process.stderr.write(`${error.message}\n`);
  process.exitCode = 1;
}
