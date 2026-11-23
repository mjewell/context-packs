/**
 * Run each pack's eval prompts: under `## Reads`, prompts that should make an agent read a doc, and under `## Skips`,
 * ones that shouldn't. A pack's prompts sit in .evals/ at its root, in a file named by the doc's path in the pack, and
 * run with that pack installed alone, plus everything inside it: for context-packs/, the top-level pack, that's the
 * whole repo. Each runs as a `claude -p` session in a copy of the pack's .evals/fixture/, or, without one, of the repo
 * for context-packs/ and of an empty folder for any other pack, and passes on whether the session read the doc.
 */
import { spawn, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createInterface } from 'node:readline';

import type { Args } from './args.ts';
import * as output from './eval_output.ts';
import * as imports from './imports.ts';
import { GEN, REPO, ROOT, local, synced, type Pack } from './packs.ts';
import { byParts, compare, exists, isDir, normpath, pjoin, resolve, walk } from './paths.ts';
import { Stack, Stop, fail } from './stop.ts';
import * as tree from './tree.ts';

const HEADING = /^## (Reads|Skips)$/;
// The CLI itself, as a .ts file run from the repo or a .js file from the npm package.
const CLI = path.join(import.meta.dirname, `cli${path.extname(import.meta.filename)}`);
// What a session's copy leaves out: history, installed dependencies, and the prompts it's being tested on.
const LEFT_OUT = ['.git', 'node_modules', '.evals'];

/**
 * A pack whose prompts eval runs: its folder, relative to the repo, and whether it's context-packs/, which runs with
 * the whole repo.
 */
export interface EvalPack {
  readonly folder: string;
  readonly top: boolean;
  readonly evals: string;
}

function evalPack(folder: string, top: boolean): EvalPack {
  return { folder, top, evals: path.join(folder, '.evals') };
}

/** A prompt, and whether a session given it should read doc, the doc at that path in the pack. */
export interface Case {
  readonly pack: EvalPack;
  readonly doc: string;
  readonly expect: 'reads' | 'skips';
  readonly prompt: string;
  /**
   * The doc as eval prints it: by its name in the block for context-packs/, and by its path in the repo for any other
   * pack, which runs on its own.
   */
  readonly name: string;
}

/** context-packs/, then each pack inside it read in place: a nested pack, or a folder an import pack names. */
function* installed(root: tree.Node, repo: string): Generator<EvalPack> {
  yield evalPack(ROOT, true);
  const stack: [Pack, tree.Node, string][] = [
    ...root.children.map((child): [Pack, tree.Node, string] => [REPO, child, pjoin(repo, synced(REPO))]),
    ...root.imports.map((i): [Pack, tree.Node, string] => [i.pack, i.root, i.source]),
  ];
  while (stack.length) {
    const [pack, node, source] = stack.shift()!;
    if (!local(pack.origin)) continue;
    yield evalPack(path.relative(repo, path.resolve(source, node.id)) || '.', false);
    stack.push(...node.children.map((child): [Pack, tree.Node, string] => [pack, child, source]));
    stack.push(...node.imports.map((i): [Pack, tree.Node, string] => [i.pack, i.root, i.source]));
  }
}

/**
 * The prompts in a doc's case file, as (expect, prompt) pairs. A prompt is a `- ` item under a `## Reads` or
 * `## Skips` heading, and goes on over the lines indented under it, as a Markdown list item does. Any other line
 * stops the run, so a forgotten indent can't split a prompt without a word.
 */
function parse(text: string, at: string): ['reads' | 'skips', string][] {
  const found: ['reads' | 'skips', string[]][] = [];
  let expect: 'reads' | 'skips' | null = null;
  text.split('\n').forEach((line, i) => {
    const heading = HEADING.exec(line);
    if (heading) {
      expect = heading[1]!.toLowerCase() as 'reads' | 'skips';
    } else if (expect && line.startsWith('- ')) {
      found.push([expect, [line.slice(2)]]);
    } else if (found.length && (line.startsWith('  ') || !line.trim())) {
      found.at(-1)![1].push(line.slice(2));
    } else if (line.trim()) {
      fail(`context-packs: ${at}:${i + 1} is neither a \`## Reads\` or \`## Skips\` heading, a \`- \` item `
           + 'under one, nor a line indented under an item. Indent it under its item, or start an item '
           + 'with `- `.');
    }
  });
  return found.map(([kind, lines]) => [kind, lines.join('\n').replace(/\n+$/, '')]);
}

/** The prompts in the pack's .evals/, but not in its fixture. */
function cases(pack: EvalPack, repo: string): Case[] {
  const evals = path.join(repo, pack.evals);
  if (!isDir(evals)) return [];
  const files = walk(evals).filter((file) => file.endsWith('.md') && !isDir(file)).sort(byParts);
  return files.flatMap((file) => {
    const doc = path.relative(evals, file);
    if (doc.split('/')[0] === 'fixture') return [];
    return parse(fs.readFileSync(file, 'utf8'), path.join(pack.evals, doc)).map(([expect, prompt]) => ({
      pack, doc, expect, prompt, name: pack.top ? doc : path.join(pack.folder, doc),
    }));
  });
}

/**
 * The import pack's text, naming a folder on disk it reads by its absolute path, so its rows point at the folder
 * itself from a copy of a fixture.
 */
function pointed(imported: imports.Import, repo: string): string {
  if (!local(imported.origin)) return imported.text;
  const front = tree.FRONT.exec(imported.text)!;
  const fields = front[1]!.split('\n').filter((line) => !line.startsWith('from: '));
  const origin = normpath(pjoin(repo, imported.origin));
  return '---\n' + [`from: ${origin}`, ...fields].join('\n') + '\n---\n' + imported.text.slice(front[0].length);
}

/** Make the copy a git repo with no history, so it syncs and its sessions run as they would in a repo. */
function init(copy: string): void {
  const result = spawnSync('git', ['init', '--quiet', copy]);
  if (result.status !== 0) throw new Error(`git init ${copy} failed: ${result.stderr}`);
}

/** Copy the folder from to to, keeping symlinks as they are, and leaving out the names skip says to. */
function copyTree(from: string, to: string, skip: (folder: string, name: string) => boolean): void {
  fs.cpSync(from, to, {
    recursive: true, verbatimSymlinks: true,
    filter: (source) => source === from || !skip(path.dirname(source), path.basename(source)),
  });
}

/**
 * Write the folder the pack's sessions run in a copy of: its fixture, or else the repo for context-packs/ or an empty
 * folder, with the pack synced into it alone, or with all of context-packs/ for the top-level pack. A folder read in
 * place is named by its absolute path, so its rows point at the folder itself from the copy.
 */
function stage(repo: string, pack: EvalPack, into: string): void {
  const fixture = path.join(repo, pack.evals, 'fixture');
  const leftOut = (_folder: string, name: string) => LEFT_OUT.includes(name);
  if (!isDir(fixture) && pack.top) {
    copyTree(repo, into, leftOut);
    init(into);
    return;
  }
  if (isDir(fixture)) {
    // Resolved, so a fixture linked from elsewhere is copied like a folder.
    copyTree(resolve(fixture), into, leftOut);
    if (exists(path.join(into, ROOT))) {
      fail(`context-packs: ${path.join(pack.evals, 'fixture')} has a ${ROOT}/ folder of its own, and eval `
           + 'puts the pack it tests there. Remove it from the fixture.');
    }
  } else {
    fs.mkdirSync(into);
  }
  if (pack.top) {
    const packs = path.join(repo, ROOT);
    copyTree(packs, path.join(into, ROOT),
             (folder, name) => leftOut(folder, name) || (folder === packs && name === path.basename(GEN)));
    for (const imported of imports.scan(repo)) {
      fs.writeFileSync(path.join(into, imported.file), pointed(imported, repo), 'utf8');
    }
  } else {
    fs.mkdirSync(path.join(into, ROOT, name(pack)), { recursive: true });
    const origin = resolve(path.join(repo, pack.folder));
    fs.writeFileSync(path.join(into, ROOT, name(pack), 'pack.md'), `---\nfrom: ${origin}\n---\n`, 'utf8');
  }
  init(into);
  const sync = spawnSync(process.execPath, [CLI, '--dir', into], { encoding: 'utf8' });
  if (sync.status !== 0) {
    fail(`context-packs: syncing ${pack.folder} into a copy of its fixture failed:\n${sync.stderr.trim()}`);
  }
}

/** The id a pack other than the top one gets in its copy. */
function name(pack: EvalPack): string {
  return path.basename(resolve(pack.folder));
}

/** Each doc the pack brings to the copy's block, by its path in the pack, with where its row points. */
function docs(copy: string, pack: EvalPack): Map<string, string> {
  const found = new Map<string, string>();
  const stack = new Stack();
  try {
    const visit = (node: tree.Node, from: Pack): void => {
      for (const doc of node.docs) {
        found.set([from.id, doc.path].filter(Boolean).join('/'), resolve(pjoin(copy, synced(from), doc.path)));
      }
      for (const child of node.children) visit(child, from);
      for (const imported of node.imports) visit(imported.root, imported.pack);
    };
    visit(tree.load(copy, stack), REPO);
  } finally {
    stack.close();
  }
  const prefix = pack.top ? '' : `${name(pack)}/`;
  return new Map([...found].filter(([doc]) => doc.startsWith(prefix)).map(([doc, at]) => [doc.slice(prefix.length), at]));
}

/**
 * How one session went: the files it read, resolved, its error if it failed, so its reads settle nothing, what claude
 * says it cost, unless it ended without saying, and how long it took.
 */
export interface Run {
  readonly read: Set<string>;
  readonly error: string | null;
  readonly costUsd: number | null;
  readonly durationMs: number;
}

/**
 * How a claude -p session given prompt in cwd went, run to its end, though reading its doc settles its case, so it
 * shows every doc it reads and what it cost. --tools leaves it only tools that look, and --allowedTools lets it use
 * them without asking; no MCP server loads, nor any settings but the copy's own.
 */
function session(prompt: string, cwd: string, model: string): Promise<Run> {
  const command = ['-p', prompt, '--output-format', 'stream-json', '--verbose', '--setting-sources', 'project',
                   '--tools', 'Read,Glob,Grep', '--allowedTools', 'Read,Glob,Grep', '--strict-mcp-config',
                   '--max-turns', '8', '--model', model];
  const read = new Set<string>();
  const start = performance.now();
  const ended = (error: string | null, costUsd: number | null = null): Run => (
    { read, error, costUsd, durationMs: Math.round(performance.now() - start) });
  return new Promise((done, failed) => {
    const child = spawn('claude', command, { cwd, stdio: ['ignore', 'pipe', 'pipe'] });
    let stderr = '';
    let result: Run | null = null;
    child.stderr.setEncoding('utf8').on('data', (chunk: string) => (stderr += chunk));
    child.on('error', failed);
    createInterface({ input: child.stdout }).on('line', (line) => {
      if (result) return;
      const message = JSON.parse(line);
      if (message.type === 'result') {
        // claude flags running out of turns as an error too, but the session just ends there, having read what it
        // read.
        const failedRun = message.is_error && message.subtype !== 'error_max_turns';
        result = ended(failedRun ? message.result : null, message.total_cost_usd ?? null);
        return;
      }
      if (message.type !== 'assistant') return;
      for (const part of message.message.content) {
        if (part.type === 'tool_use' && part.name === 'Read') read.add(resolve(part.input.file_path));
      }
    });
    child.on('close', (code) => done(
      result ?? ended(stderr.trim() || `claude exited with code ${code} without a result`)));
  });
}

/**
 * How a case's runs went: 'passed' if every run did, so a when that matches only some of the time shows up, 'errored'
 * if a session failed, or else 'failed', and how many runs passed.
 */
export interface Verdict {
  readonly outcome: 'passed' | 'failed' | 'errored';
  readonly passes: number;
}

function judge(item: Case, results: readonly Run[], doc: string, runs: number): Verdict {
  const reads = results.filter((r) => !r.error).map((r) => r.read);
  const passes = reads.filter((read) => read.has(doc) === (item.expect === 'reads')).length;
  const errored = results.some((r) => r.error);
  return { outcome: errored ? 'errored' : passes === runs ? 'passed' : 'failed', passes };
}

/** Runs jobs four at a time, calling finished with each one's index as it ends. */
async function pool<T>(jobs: readonly (() => Promise<T>)[], finished: (index: number, value: T) => void): Promise<void> {
  let next = 0;
  const worker = async (): Promise<void> => {
    while (next < jobs.length) {
      const index = next++;
      finished(index, await jobs[index]!());
    }
  };
  await Promise.all(Array.from({ length: 4 }, worker));
}

export async function run(root: tree.Node, repoPath: string, args: Args): Promise<void> {
  const repo = resolve(repoPath);
  const packs = args.pack
    ? [evalPack(path.relative(repo, resolve(path.join(repo, args.pack))) || '.', false)] : [...installed(root, repo)];
  let found = packs.flatMap((pack) => cases(pack, repo));
  if (!found.length) {
    fail('context-packs: no pack has eval prompts. Write the prompts for a doc in .evals/<doc>.md at the root '
         + 'of its pack, as `- ` items under `## Reads` and `## Skips`.');
  }
  const names = new Set(found.flatMap((item) => [item.doc, item.name]));
  const unknown = args.docs.filter((doc) => !names.has(doc));
  if (unknown.length) {
    fail(`context-packs: ${unknown.join(', ')} has no eval prompts. Docs with them: `
         + `${[...new Set(found.map((item) => item.name))].sort(compare).join(', ')}.`);
  }
  found = found.filter((item) => !args.docs.length || args.docs.includes(item.doc) || args.docs.includes(item.name));
  const staged = [...new Set(found.map((item) => item.pack))];
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'context-packs-eval-'));
  let failed = 0;
  let errored = 0;
  try {
    // Every copy is made, and every prompt matched to its doc, before any session runs.
    const copies = new Map<EvalPack, string>();
    const paths = new Map<EvalPack, Map<string, string>>();
    for (const pack of staged) {
      copies.set(pack, path.join(temp, String(copies.size)));
      stage(repo, pack, copies.get(pack)!);
      paths.set(pack, docs(copies.get(pack)!, pack));
    }
    for (const item of found) {
      if (!paths.get(item.pack)!.has(item.doc)) {
        fail(`context-packs: ${path.join(item.pack.evals, item.doc)} names no doc in ${item.pack.folder}. Name its `
             + 'file by the doc\'s path in the pack.');
      }
    }
    if (!args.json) {
      output.heading(found.length, new Set(found.map((item) => item.name)).size, args.runs, staged, repo, args.model);
    }
    const results = found.map((): Run[] => []);
    const verdicts = new Map<number, Verdict>();
    const jobs = found.flatMap((item, index) => Array.from({ length: args.runs }, () => ({ item, index })));
    let done = 0;
    await pool(jobs.map(({ item }) => () => session(item.prompt, copies.get(item.pack)!, args.model)), (job, result) => {
      const { item, index } = jobs[job]!;
      results[index]!.push(result);
      if (results[index]!.length === args.runs) {
        const doc = paths.get(item.pack)!.get(item.doc)!;
        verdicts.set(index, judge(item, results[index]!, doc, args.runs));
        if (!args.json) output.report(item, results[index]!, verdicts.get(index)!, doc, copies.get(item.pack)!, repo, args.runs);
      }
      if (!args.json) output.status(++done, jobs.length);
    });
    const outcomes = [...verdicts.values()].map((verdict) => verdict.outcome);
    failed = outcomes.filter((o) => o === 'failed').length;
    errored = outcomes.filter((o) => o === 'errored').length;
    if (args.json) {
      process.stdout.write(output.document(found.map((item, index) => (
        [item, results[index]!, verdicts.get(index)!, copies.get(item.pack)!, repo] as const)), args.model, args.runs)
        + '\n');
    } else {
      output.status(null, null);
      process.stdout.write(`${output.summary(found.length, failed, errored)}\n`);
    }
  } finally {
    fs.rmSync(temp, { recursive: true, force: true });
  }
  if (failed || errored) throw new Stop('', 1);
}
