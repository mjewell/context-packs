/** What eval prints: what it's about to run, how each prompt went as its runs finish, and how many passed. */
import path from 'node:path';

import type { Case, EvalPack, Run, Verdict } from './evals.ts';
import { compare, isDir, resolve } from './paths.ts';

const MARKS: Record<Verdict['outcome'], string> = { passed: '✓', failed: '✗', errored: '!' };

function print(line: string): void {
  process.stdout.write(`${line}\n`);
}

/** A file a session read, relative to the copy or else the repo when it's in one, as a failure lists it. */
function shown(file: string, copy: string, repo: string): string {
  for (const folder of [resolve(copy), resolve(repo)]) {
    if (file.startsWith(`${folder}/`)) return path.relative(folder, file);
  }
  return file;
}

function plural(count: number, noun: string): string {
  return `${count} ${noun}` + (count !== 1 ? 's' : '');
}

/** On a terminal, how many runs have finished, on a line the next one overwrites; null clears it. */
export function status(done: number | null, total: number | null): void {
  if (process.stdout.isTTY) process.stdout.write('\r\x1b[K' + (done !== null ? `[${done}/${total}]` : ''));
}

/** What the packs' sessions run in, as the first line says it. */
function where(packs: readonly EvalPack[], repo: string): string {
  const fixtures = packs.filter((pack) => isDir(path.join(repo, pack.evals, 'fixture'))).length;
  const repos = packs.filter((pack) => pack.top && !isDir(path.join(repo, pack.evals, 'fixture'))).length;
  const empty = packs.length - fixtures - repos;
  return [
    ...Array<string>(repos).fill('a copy of the repo'),
    ...(fixtures ? [plural(fixtures, 'fixture')] : []),
    ...(empty ? [plural(empty, 'empty folder')] : []),
  ].join(', ');
}

/** The first line: what's about to run, where, and on which model. */
export function heading(
  prompts: number,
  docs: number,
  runs: number,
  packs: readonly EvalPack[],
  repo: string,
  model: string,
): void {
  const times = runs > 1 ? `, ${runs} times each` : '';
  print(
    `Running ${plural(prompts, 'prompt')} for ${plural(docs, 'doc')}${times}, in ${where(packs, repo)}, on ${model}…`,
  );
}

/** Print how the case's runs went, with their errors, or the docs they read. */
export function report(
  item: Case,
  results: readonly Run[],
  verdict: Verdict,
  doc: string,
  copy: string,
  repo: string,
  runs: number,
): void {
  const errors = [...new Set(results.filter((r) => r.error).map((r) => r.error!))];
  const reads = results.filter((r) => !r.error).map((r) => r.read);
  status(null, null);
  const count = runs > 1 ? `${verdict.passes}/${runs}  ` : '';
  const first = item.prompt.split('\n')[0];
  print(`${MARKS[verdict.outcome]} ${item.name}  ${item.expect}  ${count}${first}`);
  for (const error of errors) print(`    error: ${error}`);
  const docs = [
    ...new Set(
      reads
        .flatMap((read) => [...read])
        .filter((file) => path.extname(file) === '.md')
        .map((file) => shown(file, copy, repo)),
    ),
  ].sort(compare);
  const others = docs.filter((file) => file !== shown(doc, copy, repo));
  if (verdict.outcome === 'failed') {
    print(docs.length ? `    read: ${docs.join(', ')}` : '    read no docs');
  } else if (verdict.outcome === 'passed' && others.length) {
    // Other docs a passing session read, since a row firing where it shouldn't shows up here first.
    print(`    also read: ${others.join(', ')}`);
  }
}

/**
 * Every case, in the order its file gives it, as (case, its runs, its verdict, the copy it ran in, the repo), with
 * each run's files, as JSON.
 */
export function document(
  cases: readonly (readonly [Case, readonly Run[], Verdict, string, string])[],
  model: string,
  runs: number,
): string {
  return JSON.stringify(
    {
      model,
      runs,
      cases: cases.map(([item, results, verdict, copy, repo]) => ({
        doc: item.name,
        expect: item.expect,
        prompt: item.prompt,
        outcome: verdict.outcome,
        passes: verdict.passes,
        runs: results.map((result) => ({
          read: [...result.read].map((file) => shown(file, copy, repo)).sort(compare),
          error: result.error,
          cost_usd: result.costUsd,
          duration_ms: result.durationMs,
        })),
      })),
    },
    null,
    2,
  );
}

/** The last line: how many passed, or how many failed and errored. */
export function summary(total: number, failed: number, errored: number): string {
  if (!failed && !errored) return `${total} passed`;
  if (!errored) return `${failed} of ${total} failed`;
  if (!failed) return `${errored} of ${total} errored`;
  return `${failed} of ${total} failed, ${errored} errored`;
}
