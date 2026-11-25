/**
 * What a finding is, as the review's modules read one. The contract is findings.schema.json in review/prompts/: agents
 * read it, and errors() checks every answer against it before any of these types describe the value. So a change to
 * the schema is made here too, by hand.
 */
import { findingsSchema } from './schema.ts';

export type Kind = 'deviation' | 'conflict' | 'uncovered choice';

// The kinds, in the order the findings schema lists them, which is the order the review counts them in. Each is a noun
// that takes an s for more than one.
export const KINDS = findingsSchema().properties!.findings!.items!.properties!.kind!.enum as readonly Kind[];

/** A rule a finding quotes: its file from the repo root, its text, and whether its doc reached the work. */
export interface Rule {
  readonly file: string;
  readonly quote: string;
  readonly routed: boolean;
}

/** A line at the head where a finding applies, and whether the code there follows the rule. */
export interface Spot {
  readonly path: string;
  readonly line: number;
  readonly follows: boolean;
}

/** For an uncovered choice, one way the existing code makes it, with examples as path:line. */
export interface Exemplar {
  readonly way: string;
  readonly examples: readonly string[];
}

export interface Finding {
  readonly kind: Kind;
  readonly headline: string;
  readonly rules: readonly Rule[];
  readonly spots: readonly Spot[];
  readonly deliberate: readonly string[];
  readonly exemplars: readonly Exemplar[];
  readonly take: string;
}

/**
 * A finding as CI's summary carries it: thread is the review thread pack-review opened for it on an earlier run, and
 * commentary sums up what that thread's replies say about it. Either is null when there's none.
 */
export interface CiFinding extends Finding {
  readonly thread: string | null;
  readonly commentary: string | null;
}

/** A finding in a run's findings: a local run's have no thread or commentary, and from-pr's have them from CI. */
export type RunFinding = Finding & Partial<CiFinding>;

/** A run folder's findings.json, which the run's finish() writes. */
export interface RunFindings {
  readonly base: string;
  readonly head: string;
  readonly findings: readonly RunFinding[];
}

/** The line a finding's thread opens on, or null when the diff shows none of its spots. */
export type Anchor = { readonly path: string; readonly line: number } | null;

/** The review job's report.json, which report.ts writes for the pairing and post jobs. */
export interface Report {
  readonly base: string;
  readonly base_ref: string;
  readonly head: string;
  readonly findings: readonly Finding[];
  readonly anchors: readonly Anchor[];
}

/** The JSON in the summary comment's findings block, which the local run's from-pr reads. */
export interface SummaryBlock {
  readonly base: string;
  readonly base_ref: string;
  readonly head: string;
  readonly findings: readonly CiFinding[];
}
