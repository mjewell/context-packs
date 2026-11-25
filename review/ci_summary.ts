/**
 * The summary a CI review posted on a PR, read for a local run with the user's own GitHub login. That login isn't the
 * token's identity that posted it, so a comment counts as pack-review's when the workflow's bot wrote it and it ends
 * with the marker, rather than by viewerDidAuthor as CI's own steps tell it.
 */
import { spawnSync } from 'node:child_process';

import { Refused } from './change.ts';
import * as github from './github.ts';
import type { Finding } from './report.ts';
import { errors, findingsSchema, type Schema } from './schema.ts';
import { TITLE } from './summary.ts';

const SUMMARY_COMMENTS = `
query SummaryComments($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      headRefOid baseRefName
      comments(first: ${github.PAGE}) { pageInfo { hasNextPage } nodes { author { login } body bodyText } }
    }
  }
}`;

interface SummaryComment {
  readonly author: { readonly login: string } | null;
  readonly body: string;
  readonly bodyText: string;
}

/**
 * A finding as CI's summary carries it: thread is the review thread pack-review opened for it on an earlier run, and
 * commentary sums up what that thread's replies say about it. Either is null when there's none.
 */
export interface CiFinding extends Finding {
  readonly thread: string | null;
  readonly commentary: string | null;
}

/** The report CI's summary carries, as the summary's JSON block holds it. */
export interface Report {
  readonly base: string;
  readonly base_ref: string;
  readonly head: string;
  readonly findings: CiFinding[];
}

/** A PR as a user names it, owner/repo#number. */
export interface Pr {
  readonly owner: string;
  readonly name: string;
  readonly number: number;
}

export function pr(text: string): Pr {
  const match = /^([\w.-]+)\/([\w.-]+)#(\d+)$/.exec(text);
  if (!match) throw new Refused(`${text} isn't a PR: name it as owner/repo#number.`);
  return { owner: match[1]!, name: match[2]!, number: Number(match[3]) };
}

/** The token of the user's gh login. */
function token(): string {
  const run = spawnSync('gh', ['auth', 'token'], { encoding: 'utf8' });
  if (run.status !== 0) {
    throw new Refused(
      `gh has no token for GitHub: ${String(run.stderr ?? run.error).trim()}. Log in with gh auth login.`,
    );
  }
  return run.stdout.trim();
}

/** The PR's head and base branch now, and the report in pack-review's summary on it. */
export async function read(
  target: Pr,
  bot: string,
): Promise<{ readonly head: string; readonly baseRef: string; readonly report: Report }> {
  const found = await github.graphql<{
    repository: {
      pullRequest: { headRefOid: string; baseRefName: string; comments: github.Connection<SummaryComment> };
    };
  }>('SummaryComments', SUMMARY_COMMENTS, { ...target }, token());
  const pull = found.repository.pullRequest;
  const comments = github.nodes(pull.comments, 'comments');
  const blocks = (comment: SummaryComment) => comment.body.split(`<summary>${TITLE}</summary>`).length - 1;
  const withBlocks = comments.filter((comment) => blocks(comment));
  if (!withBlocks.length) {
    throw new Refused(
      "The PR has no summary from pack-review, so CI hasn't reviewed it. Find the findings here with pack-findings.",
    );
  }
  const byBot = (comment: SummaryComment) => comment.author?.login === bot;
  const marked = (comment: SummaryComment) => comment.body.trimEnd().endsWith(github.MARKER);
  const [summary] = withBlocks;
  if (withBlocks.length > 1 || !byBot(summary!) || !marked(summary!) || blocks(summary!) !== 1) {
    const lines = withBlocks.map(
      (comment, n) =>
        `  comment ${n + 1}: by ${byBot(comment) ? bot : `someone other than ${bot}`}, ` +
        `${blocks(comment)} block${blocks(comment) !== 1 ? 's' : ''}, ` +
        `${marked(comment) ? 'ends' : "doesn't end"} with the marker\n`,
    );
    throw new Refused(
      `Stop, and show the user this: pack-review's summary is one comment by ${bot}, with one findings block, that ` +
        "ends with pack-review's marker. The PR's comments with a findings block don't fit that:\n" +
        lines.join('').trimEnd(),
    );
  }
  let report: unknown;
  try {
    report = JSON.parse(summary!.bodyText.split(`${TITLE}\n`)[1]!);
  } catch (error) {
    if (!(error instanceof SyntaxError)) throw error;
    throw new Refused(
      "Stop, and show the user this: pack-review's summary on the PR holds no JSON this version can read after its " +
        `findings block's title: ${error.message}.`,
    );
  }
  const broken = reportErrors(report);
  if (broken.length) {
    throw new Refused(
      "Stop, and show the user this: pack-review's summary on the PR doesn't fit the findings this version of the " +
        `review reads, so CI may have run another version:\n${broken.map((line) => `  ${line}`).join('\n')}`,
    );
  }
  return { head: pull.headRefOid, baseRef: pull.baseRefName, report: report as Report };
}

const REPORT: Schema = {
  type: 'object',
  additionalProperties: false,
  required: ['base', 'base_ref', 'head', 'findings'],
  properties: {
    base: { type: 'string' },
    base_ref: { type: 'string' },
    head: { type: 'string' },
    findings: { type: 'array', items: { type: 'object' } },
  },
};

/**
 * Each way a summary's report breaks the shape this version reads. Its findings are checked against the findings
 * schema, without thread and commentary, which the schema can't express since each is a string or null.
 */
function reportErrors(report: unknown): string[] {
  const top = errors(report, REPORT);
  if (top.length) return top;
  const findings = (report as { findings: Record<string, unknown>[] }).findings;
  const core = findings.map(({ thread: _, commentary: __, ...rest }) => rest);
  const extras = findings.flatMap((finding, n) =>
    (['thread', 'commentary'] as const)
      .filter((key) => !(typeof finding[key] === 'string' || finding[key] === null))
      .map((key) => `findings[${n}].${key} must be a string or null`),
  );
  return [...errors({ findings: core }, findingsSchema()), ...extras];
}
