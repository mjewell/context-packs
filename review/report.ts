#!/usr/bin/env node
import fs from 'node:fs';
/**
 * Write the review job's report for the pairing and post jobs: the findings the wizard built, cleaned again, and the
 * line each one's thread can open on. findingsIn() builds findings from the finders' findings each of the merging
 * agent's groups names, for the wizard's submit-groups. It reaches nothing outside the runner.
 */
import { isDeepStrictEqual } from 'node:util';

import { parse } from '../src/argparse.ts';
import { runAsScript } from '../src/main.ts';
import { repr } from '../src/pystr.ts';
import { clean } from './sanitize.ts';

interface Spot {
  readonly path: string;
  readonly line: number;
  readonly follows: boolean;
}

export interface Finding {
  readonly kind: string;
  readonly headline: string;
  readonly rules: unknown[];
  readonly spots: Spot[];
  readonly deliberate: unknown[];
  readonly exemplars: unknown[];
  readonly take: string;
}

/** A finder's finding, with the id the merging agent's groups name it by. */
export interface Source {
  readonly id: string;
  readonly finding: Finding;
}

interface Group {
  readonly ids: string[];
  readonly kind: string;
  readonly headline: string;
  readonly take: string;
}

/** The agent's findings with invisible characters removed and secrets redacted from every string. */
function cleaned<T>(value: T): T {
  if (typeof value === 'string') return clean(value) as T;
  if (Array.isArray(value)) return value.map(cleaned) as T;
  if (value !== null && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, cleaned(item)])) as T;
  }
  return value;
}

/** Groups the report can't be built from, with the reason. */
export class Rejected extends Error {}

function groupsIn(text: string): Group[] {
  let output: unknown;
  try {
    output = JSON.parse(text);
  } catch {
    output = null;
  }
  const groups =
    output !== null && typeof output === 'object' && !Array.isArray(output)
      ? (output as Record<string, unknown>).groups
      : undefined;
  if (!Array.isArray(groups))
    throw new Rejected(`the merge returned no groups: ${repr([...text].slice(0, 500).join(''))}`);
  return groups as Group[];
}

/** The items in order, each once, by value. */
function unique<T>(items: readonly T[]): T[] {
  return items.filter((item, n) => !items.slice(0, n).some((earlier) => isDeepStrictEqual(earlier, item)));
}

/**
 * The finding a group makes: its kind, headline and take, and every rule, spot, sign and exemplar of the finders'
 * findings it names. A spot two of them disagree on deviates, since it goes against at least one rule.
 */
function built(group: Group, sources: ReadonlyMap<string, Finding>): Finding {
  const found = group.ids.map((id) => sources.get(id)!);
  const spots = new Map<string, Spot>();
  for (const spot of found.flatMap((finding) => finding.spots)) {
    const key = JSON.stringify([spot.path, spot.line]);
    const earlier = spots.get(key);
    spots.set(key, earlier ? { ...spot, follows: earlier.follows && spot.follows } : spot);
  }
  return {
    kind: group.kind,
    headline: group.headline,
    rules: unique(found.flatMap((finding) => finding.rules)),
    spots: [...spots.values()],
    deliberate: unique(found.flatMap((finding) => finding.deliberate)),
    exemplars: unique(found.flatMap((finding) => finding.exemplars)),
    take: group.take,
  };
}

/**
 * The groups, when they name every finder's finding exactly once and no other. A finding left out or named twice
 * would drop or repeat what a finder found without anything failing.
 */
function checked(groups: Group[], sources: ReadonlyMap<string, Finding>): Group[] {
  const named = groups.flatMap((group) => group.ids);
  const invented = unique(named.filter((id) => !sources.has(id)));
  if (invented.length) throw new Rejected(`the merge's groups name ${invented.join(', ')}, which no finder reported`);
  const repeated = unique(named.filter((id, n) => named.slice(0, n).includes(id)));
  if (repeated.length) throw new Rejected(`the merge's groups put ${repeated.join(', ')} in more than one group`);
  const left = [...sources.keys()].filter((id) => !named.includes(id));
  if (left.length) throw new Rejected(`the merge's groups leave out ${left.join(', ')}`);
  return groups;
}

/** The findings that the merging agent's groups, its answer's JSON text, build from the finders' findings. */
export function findingsIn(groupsText: string, listed: readonly Source[]): Finding[] {
  const sources = new Map(listed.map((source) => [source.id, source.finding]));
  return cleaned(checked(groupsIn(groupsText), sources).map((group) => built(group, sources)));
}

/** The findings a review's wizard built, cleaned like the merge's, once they're for the head that was reviewed. */
function builtByWizard(file: string, head: string): Finding[] {
  const found: { head: string; findings: Finding[] } = JSON.parse(fs.readFileSync(file, 'utf8'));
  if (found.head !== head) throw new Rejected(`the review's findings are for ${found.head}, not the head, ${head}`);
  return cleaned(found.findings);
}

/**
 * The spot each finding's thread can open on: its first spot that deviates and the diff shows, or else its first spot
 * the diff shows, or null when the diff shows none, since a review comment needs a line in the diff.
 */
function anchors(findings: readonly Finding[], shown: Readonly<Record<string, number[]>>) {
  return findings.map((finding) => {
    const spots = finding.spots
      .filter((spot) => (shown[spot.path] ?? []).includes(spot.line))
      .sort((a, b) => Number(a.follows) - Number(b.follows));
    return spots[0] ? { path: spots[0].path, line: spots[0].line } : null;
  });
}

function main(): void {
  const string = (flag: string, help: string) => ({
    flag,
    dest: flag.slice(2).replace('-', '_'),
    metavar: flag.slice(2).toUpperCase().replace('-', '_'),
    required: true as const,
    help,
  });
  const args = parse(
    {
      prog: 'report.ts',
      help: '',
      options: [
        string('--base', 'the commit the reviewed change starts from'),
        string('--base-ref', 'the branch the PR was to merge into when it was reviewed'),
        string('--head', 'the commit that was reviewed'),
        string('--findings', "the findings the review's wizard built"),
        string('--shown', 'the head lines each diff shows, as `change.ts shown` prints them'),
        string('--out', 'where to write the report'),
      ],
    },
    process.argv.slice(2),
  ) as Record<string, string>;
  let findings: Finding[];
  try {
    findings = builtByWizard(args.findings!, args.head!);
  } catch (error) {
    if (!(error instanceof Rejected)) throw error;
    process.stderr.write(`pack-review: ${error.message}.\n`);
    process.exit(1);
  }
  const report = {
    base: args.base,
    base_ref: args.base_ref,
    head: args.head,
    findings,
    anchors: anchors(findings, JSON.parse(fs.readFileSync(args.shown!, 'utf8'))),
  };
  fs.writeFileSync(args.out!, JSON.stringify(report), 'utf8');
}

if (runAsScript(import.meta.filename)) main();
