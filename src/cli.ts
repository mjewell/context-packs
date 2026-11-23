#!/usr/bin/env node
/**
 * Sync context packs into a repository, or any folder such as the one above the repositories: the packs in
 * context-packs/, the repo's own and those its import packs name, as one block in AGENTS.md, with the docs of packs from
 * git and the indexes of nested packs in context-packs/gen/.
 */
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { type Args, parse } from './args.ts';
import { block, header, instructions, region, snapshot, type Region } from './blocks.ts';
import * as evals from './evals.ts';
import * as imports from './imports.ts';
import { GEN, REPO, base, synced } from './packs.ts';
import { exists, isDir, lexists, pjoin, walk } from './paths.ts';
import { Stack, Stop, fail } from './stop.ts';
import * as syncReport from './sync_report.ts';
import * as tables from './tables.ts';
import * as tree from './tree.ts';

/** Each import pack: its id, where its pack comes from, and its pin. */
function show(found: readonly imports.Import[]): void {
  for (const i of found) {
    process.stdout.write(`${i.id}  ${i.origin}${i.path ? `  ${i.path}` : ''}${i.ref ? ` @ ${i.ref}` : ''}\n`);
  }
}

/** Write the generated files into out's context-packs/gen/, and return the block, whose hash covers them. */
function generate(root: tree.Node, out: string, repo: string): string {
  const start = base(repo);
  tree.write(root, REPO, pjoin(repo, synced(REPO)), out, start);
  const rendered = tree.render(root, REPO, start);
  return block(header(start) + (rendered ? '\n' : '') + rendered, snapshot(path.join(out, GEN)));
}

/** The files in out's context-packs/gen/, by their path in the synced repo. */
function generated(out: string): Map<string, Buffer> {
  const folder = path.join(out, GEN);
  if (!isDir(folder)) return new Map();
  return new Map(walk(folder).filter((file) => fs.statSync(file).isFile())
    .map((file) => [path.join(GEN, path.relative(folder, file)), fs.readFileSync(file)]));
}

/**
 * Stop, naming what a sync would change, if the block or a generated file differs from what it would write into out.
 * The block's hash covers the generated files, so any change to them changes the block too.
 */
function check(file: string, found: Region, written: string, out: string, repo: string): void {
  if (!exists(file)) {
    fail(`context-packs: ${file} doesn't exist, so the repo was never synced. Run \`npx context-packs\` and `
         + 'commit the result.');
  }
  if (written === found.block) return;
  const [fresh, current] = [generated(out), generated(repo)];
  const differs = (a?: Buffer, b?: Buffer) => (a && b ? !a.equals(b) : a !== b);
  const stale = [...new Set([...fresh.keys(), ...current.keys()])].filter((p) => differs(fresh.get(p), current.get(p)))
    .sort();
  fail(`context-packs: ${file}: the context-packs block is stale`
       + (stale.length ? ', as are these generated files:\n\n' + stale.map((p) => `  ${p}\n`).join('') : '.\n')
       + '\nRun `npx context-packs` and commit the result.');
}

async function sync(args: Args): Promise<void> {
  const repo = args.dir;
  if (!isDir(repo)) fail(`context-packs: ${repo} is not a folder`);

  const file = instructions(repo);
  const found = region(repo, file);
  const before = imports.scan(repo);
  if (args.command === 'list') {
    show(before);
    return;
  }
  if (args.command === 'docs') {
    process.stdout.write(tables.units(repo, found.block).map((unit) => unit.map((p) => `${p}\n`).join('')).join('\n'));
    return;
  }
  const edits = imports.command(args, repo, before);

  let written = '';
  let created = false;
  await imports.applied(repo, edits, async () => {
    const stack = new Stack();
    try {
      const root = tree.load(repo, stack);
      if (args.command === 'check' || args.command === 'eval') {
        const out = fs.mkdtempSync(path.join(os.tmpdir(), 'context-packs-check-'));
        stack.defer(() => fs.rmSync(out, { recursive: true, force: true }));
        check(file, found, generate(root, out, repo), out, repo);
        // Cases run against the block as it is, so a stale one would test rows that are about to change.
        if (args.command === 'eval') await evals.run(root, repo, args);
        return;
      }
      if (exists(path.join(repo, GEN))) fs.rmSync(path.join(repo, GEN), { recursive: true, force: true });
      written = generate(root, repo, repo);
      const text = found.text.slice(0, found.start) + written + found.text.slice(found.end);
      created = !exists(file);
      fs.writeFileSync(file, text, 'utf8');
    } finally {
      stack.close();
    }
  });
  if (args.command === 'check' || args.command === 'eval') return;
  // A new AGENTS.md gets CLAUDE.md linked to it, so Claude Code reads it too. A repo that already has its own
  // instruction files keeps them as they are.
  const linked = created && !lexists(path.join(repo, 'CLAUDE.md'));
  if (linked) fs.symlinkSync('AGENTS.md', path.join(repo, 'CLAUDE.md'));
  const updating = args.command === 'update'
    ? before.filter((i) => !args.ids.length || args.ids.includes(i.id)).map((i) => i.id) : [];
  for (const line of syncReport.changes(found, written, created, linked, before, imports.scan(repo), updating)) {
    process.stdout.write(`${line}\n`);
  }
}

/** The review's wizard, which is still Python, with everything after `review` handed on. */
function review(argv: readonly string[]): never {
  const wizard = path.join(import.meta.dirname, '..', 'review', 'wizard.py');
  const result = spawnSync('python3', [wizard, ...argv], { stdio: 'inherit' });
  if (result.error) fail(`context-packs: couldn't run python3 (${result.error.message}). Install Python 3.9 or later.`);
  process.exit(result.status ?? 1);
}

async function main(): Promise<void> {
  const argv = process.argv.slice(2);
  if (argv[0] === 'review') review(argv.slice(1));
  try {
    await sync(parse(argv, process.cwd()));
  } catch (error) {
    if (!(error instanceof Stop)) throw error;
    if (error.message) process.stderr.write(`${error.message}\n`);
    process.exitCode = error.code;
  }
}

await main();
