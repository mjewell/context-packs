/** A PR on a fake GitHub, and a folder for the files the review scripts read and write. */
import path from 'node:path';

import { Case } from './case.ts';
import { comment, connection, FakeGitHub, said } from './fake_github.ts';
import { command, environment, type Result, ROOT, run } from './scripts.ts';
import { tempDir } from './temp.ts';

export const REVIEW = path.join(ROOT, 'review');
export const SCHEMA = path.join(ROOT, 'skills', 'pack-findings', 'findings.schema.json');
export const MARKER = '<!-- pack-review -->';
export { BASE, HEAD } from './fake_github.ts';

/** A spot a finding names, which deviates from the rule unless follows. */
export function spot(file: string, line: number, follows = false) {
  return { path: file, line, follows };
}

/** A comment pack-review posted earlier. */
export function own(body: string, id = 'IC_1') {
  return comment(`🤖 ${body}\n\n${MARKER}`, { mine: true, id });
}

/** The comment pack-review opens a thread with. */
export function ours(text = 'A game number in sim code.', { id = 'RC_1', minimized = null as string | null } = {}) {
  return said(text, { author: 'github-actions', bot: true, mine: true, body: `${text}\n\n${MARKER}`, id, minimized });
}

/**
 * A pack-review thread on src/sim.ts:42 as GitHub's GraphQL API returns it: the comment pack-review opened it with,
 * then replies.
 */
export function reviewThread(id: string, { resolved = false, replies = [] as readonly unknown[] } = {}) {
  return {
    id,
    path: 'src/sim.ts',
    line: 42,
    isResolved: resolved,
    comments: connection([ours(undefined, { id: `${id}_c` }), ...replies]),
  };
}

/** A PR, number 7 in o/r, on a fake GitHub, and a folder for the files the review scripts read and write. */
export class ReviewCase extends Case {
  root!: string;
  github!: FakeGitHub;
  env!: NodeJS.ProcessEnv;

  protected override async setUp(): Promise<void> {
    this.root = tempDir(this.t, 'context-packs-review-');
    this.github = await FakeGitHub.start(this.t);
    this.env = environment({
      GITHUB_TOKEN: 'token-1',
      GITHUB_REPOSITORY: 'o/r',
      GITHUB_API_URL: this.github.url,
      GITHUB_GRAPHQL_URL: `${this.github.url}/graphql`,
    });
  }

  /** Runs review/<name>.ts in the case's folder. */
  script(name: string, ...args: (string | number)[]): Promise<Result> {
    return run([...command(`review/${name}`), ...args.map(String)], { cwd: this.root, env: this.env });
  }

  /** The variables each request for the operation sent. */
  sent(operation: string): Record<string, unknown>[] {
    return this.github.requests
      .filter((request) => request.operationName === operation)
      .map((request) => request.variables!);
  }
}
