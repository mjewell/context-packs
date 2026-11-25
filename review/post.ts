#!/usr/bin/env node
/**
 * Post the review: a GitHub review that opens a thread for each finding no thread was opened for, a reply in a
 * pack-review thread only when there's something to say, then the one summary comment. No review is ever left
 * pending: the new threads are submitted as they're created and each reply is posted on its own, so a write that fails
 * or a run that's cancelled leaves only comments the next run can pick up from. It runs in the post job, which has no
 * agent. It plans every write and checks the plan before the first one, so a run that stops on a check leaves the PR
 * as it was. It reads pack-review's threads afresh through trust.ts, so it writes only to threads pack-review opened on
 * this PR.
 */
import fs from 'node:fs';

import { parse } from '../src/argparse.ts';
import { fail, Stop } from '../src/stop.ts';
import type { Report } from './finding.ts';
import * as findingComment from './finding_comment.ts';
import * as github from './github.ts';
import * as summary from './summary.ts';
import * as trust from './trust.ts';

const ADD_REVIEW = `mutation AddReview($input: AddPullRequestReviewInput!) {
  addPullRequestReview(input: $input) { pullRequestReview { id } } }`;
const ADD_REPLY = `mutation AddReply($input: AddPullRequestReviewThreadReplyInput!) {
  addPullRequestReviewThreadReply(input: $input) { comment { id } } }`;
const ADD_COMMENT = 'mutation AddComment($input: AddCommentInput!) { addComment(input: $input) { clientMutationId } }';
const UPDATE_COMMENT = `mutation UpdateComment($input: UpdateIssueCommentInput!) {
  updateIssueComment(input: $input) { clientMutationId } }`;

const STILL_FOUND = 'still found';

interface Paired {
  readonly pairs: readonly { readonly finding: number; readonly thread: string }[];
  readonly commentary: readonly { readonly finding: number; readonly text: string }[];
}

interface NewThread {
  readonly path: string;
  readonly line: number;
  readonly side: 'RIGHT';
  readonly body: string;
}

/**
 * Whether pack-review's last word in the thread is already that its finding is still found. Its bodyText drops the
 * code spans, so it reads "🤖 still found <sha>".
 */
function told(thread: trust.Thread): boolean {
  const last = thread.comments.at(-1)!;
  return 'ours' in last && last.ours && last.text.startsWith(`🤖 ${STILL_FOUND}`);
}

/**
 * The reply in a thread whose finding the review still finds, or null when it has nothing to say. It leads with the
 * commit as a tag, and `still found` before it when the thread was resolved.
 */
function reply(head: string, resolved: boolean, commentary: string | undefined): string | null {
  const lead = resolved ? `\`${STILL_FOUND}\` \`${head.slice(0, 7)}\`` : `\`${head.slice(0, 7)}\``;
  if (commentary === undefined) return resolved ? github.signed(lead) : null;
  return github.signed(`${lead}\n\n${findingComment.quoted(commentary)}`);
}

/** Why the PR no longer matches what was reviewed, or null when it does. */
function stale(report: Report, pr: github.PullRequest): string | null {
  if (pr.headRefOid !== report.head) {
    return (
      `the PR moved on to ${pr.headRefOid} since this review of ${report.head}, so it posts nothing. ` +
      'The run for the newer commit will.'
    );
  }
  if (pr.baseRefName !== report.base_ref) {
    return (
      `the PR moved from ${report.base_ref} to ${pr.baseRefName} since this review, so it posts ` +
      'nothing. The run for the new base will.'
    );
  }
  return null;
}

/**
 * Every write the review makes: the new threads, the replies by thread id, and the summary's body with the id of the
 * summary it replaces, or null when it adds one. It stops on anything that would fail partway through posting.
 */
function planned(
  repo: string,
  number: number,
  report: Report,
  paired: Paired,
  pr: github.PullRequest,
  threads: ReadonlyMap<string, trust.Thread>,
): [NewThread[], Map<string, string>, [string, string | null]] {
  const { head, findings } = report;
  const pairs = new Map(paired.pairs.map((pair) => [pair.finding, pair.thread]));
  const commentary = new Map(paired.commentary.map((item) => [item.finding, item.text]));
  for (const thread of pairs.values()) {
    if (!threads.has(thread))
      fail(`pack-review: the pairs name ${thread}, which isn't one of pack-review's threads on this PR.`);
  }
  const added: NewThread[] = [];
  const replies = new Map<string, string>();
  findings.forEach((finding, n) => {
    const anchor = report.anchors[n] ?? null;
    const thread = pairs.get(n);
    if (thread === undefined) {
      if (anchor !== null) {
        added.push({
          path: anchor.path,
          line: anchor.line,
          side: 'RIGHT',
          body: findingComment.body(finding, head, anchor),
        });
      }
      return;
    }
    // A resolved thread hears its finding is still found once, until someone comments after that.
    const resolved = threads.get(thread)!.resolved && !told(threads.get(thread)!);
    const body = reply(head, resolved, commentary.get(n));
    if (body !== null) replies.set(thread, body);
  });
  const body = summary.body(repo, number, {
    ...report,
    findings: findings.map((finding, n) => ({
      ...finding,
      thread: pairs.get(n) ?? null,
      commentary: commentary.get(n) ?? null,
    })),
  });
  const length = [...body].length;
  if (length > summary.LIMIT)
    fail(`pack-review: the summary is ${length} characters, and GitHub allows ${summary.LIMIT} in a comment.`);
  const summaries = pr.comments.filter(github.own).map((comment) => comment.id);
  if (summaries.length > 1) {
    fail(`pack-review: the PR has more than one pack-review summary (${summaries.join(', ')}). Delete all but one.`);
  }
  return [added, replies, [body, summaries[0] ?? null]];
}

async function main(): Promise<void> {
  const args = parse(
    {
      prog: 'post.ts',
      help: '',
      options: [
        { flag: '--pr', dest: 'pr', metavar: 'PR', required: true, help: 'the PR number' },
        {
          flag: '--report',
          dest: 'report',
          metavar: 'REPORT',
          required: true,
          help: "the find job's report, from report.ts",
        },
        {
          flag: '--paired',
          dest: 'paired',
          metavar: 'PAIRED',
          required: true,
          help: "the pairing job's pairs and commentary",
        },
      ],
    },
    process.argv.slice(2),
  );
  const number = Number(args.pr);
  const report: Report = JSON.parse(fs.readFileSync(String(args.report), 'utf8'));
  const paired: Paired = JSON.parse(fs.readFileSync(String(args.paired), 'utf8'));
  const pr = await github.pullRequest(number);
  const why = stale(report, pr);
  if (why) {
    process.stdout.write(`pack-review: ${why}\n`);
    return;
  }
  const threads = new Map((await trust.threads(number)).map((thread) => [thread.id, thread]));
  const [added, replies, [body, existing]] = planned(
    process.env.GITHUB_REPOSITORY!,
    number,
    report,
    paired,
    pr,
    threads,
  );
  if (added.length) {
    await github.graphql('AddReview', ADD_REVIEW, {
      input: {
        pullRequestId: pr.id,
        commitOID: report.head,
        event: 'COMMENT',
        threads: added,
      },
    });
  }
  for (const [thread, text] of replies) {
    // A reply joins a review only while that review is pending, so each one is posted on its own.
    try {
      await github.graphql('AddReply', ADD_REPLY, { input: { pullRequestReviewThreadId: thread, body: text } });
    } catch (error) {
      if (!(error instanceof github.GitHubError)) throw error;
      fail(`pack-review: in thread ${thread}: ${error.message}`);
    }
  }
  if (existing) await github.graphql('UpdateComment', UPDATE_COMMENT, { input: { id: existing, body } });
  else await github.graphql('AddComment', ADD_COMMENT, { input: { subjectId: pr.id, body } });
  process.stdout.write(
    `pack-review: opened ${added.length} threads, replied in ${replies.size}, and posted the summary of ` +
      `${report.findings.length} findings.\n`,
  );
}

try {
  await main();
} catch (error) {
  if (error instanceof github.GitHubError) {
    process.stderr.write(`pack-review: ${error.message}\n`);
    process.exitCode = 1;
  } else if (error instanceof Stop) {
    process.stderr.write(`${error.message}\n`);
    process.exitCode = error.code;
  } else {
    throw error;
  }
}
