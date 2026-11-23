/** GitHub's API, as the review scripts use it. Reads the token, the repo and the API's URLs from the variables GitHub Actions sets. */

// Ends every comment pack-review writes, so its own comments can be told from others the same token wrote.
export const MARKER = '<!-- pack-review -->';
const PAGE = 100;

const PULL_REQUEST = `
query PullRequest($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      id headRefOid baseRefName
      comments(first: ${PAGE}) { pageInfo { hasNextPage } nodes { id viewerDidAuthor body } }
    }
  }
}`;

/** GitHub refused a request, or answered with more than pack-review reads. code is the HTTP status, if any. */
export class GitHubError extends Error {
  readonly code: number | null;

  constructor(message: string, code: number | null = null) {
    super(message);
    this.code = code;
  }
}

export interface Comment {
  readonly id: string;
  readonly viewerDidAuthor: boolean;
  readonly body: string;
}

export interface PullRequest {
  readonly id: string;
  readonly headRefOid: string;
  readonly baseRefName: string;
  readonly comments: Comment[];
}

interface Connection<T> {
  readonly pageInfo: { readonly hasNextPage: boolean; readonly endCursor?: string };
  readonly nodes: T[];
}

export function repository(): [string, string] {
  return process.env.GITHUB_REPOSITORY!.split('/') as [string, string];
}

/** GitHub's answer: to a POST of body, or to a GET when body is undefined. */
async function send(url: string, body: unknown, what: string): Promise<any> {
  const response = await fetch(url, {
    method: body === undefined ? 'GET' : 'POST',
    body: body === undefined ? undefined : JSON.stringify(body),
    headers: {
      Authorization: `bearer ${process.env.GITHUB_TOKEN}`, 'Content-Type': 'application/json',
      Accept: 'application/vnd.github+json',
    },
  });
  if (response.ok) return response.json();
  let answer = await response.text();
  try {
    const found = JSON.parse(answer);
    answer = [found.message ?? '', ...(found.errors ?? []).map((e: any) => e.message ?? JSON.stringify(e))].join('; ');
  } catch {
    // Not JSON: GitHub's text says why.
  }
  throw new GitHubError(`GitHub refused ${what} with HTTP ${response.status}: ${answer}`, response.status);
}

/** The data GitHub answers the operation with. */
export async function graphql(operation: string, query: string, variables: Record<string, unknown>): Promise<any> {
  const url = process.env.GITHUB_GRAPHQL_URL || 'https://api.github.com/graphql';
  const answer = await send(url, { operationName: operation, query, variables }, operation);
  if (answer.errors?.length) {
    throw new GitHubError(`GitHub refused ${operation}: ` + answer.errors.map((e: { message: string }) => e.message).join('; '));
  }
  return answer.data;
}

/** What GitHub's REST API answers a GET of path with. */
export async function rest(path: string): Promise<any> {
  return send((process.env.GITHUB_API_URL || 'https://api.github.com') + path, undefined, path);
}

/** A list's items, refusing one with another page, since a review that silently missed some would be wrong. */
function nodes<T>(connection: Connection<T>, listing: string): T[] {
  if (connection.pageInfo.hasNextPage) {
    throw new GitHubError(`The PR has more than ${PAGE} ${listing}, and pack-review reads only one page of them.`);
  }
  return connection.nodes;
}

/** The PR's id, head, base branch and comments, checked to fit on one page. */
export async function pullRequest(number: number): Promise<PullRequest> {
  const [owner, name] = repository();
  const data = await graphql('PullRequest', PULL_REQUEST, { owner, name, number });
  const pr = data.repository.pullRequest;
  return { ...pr, comments: nodes(pr.comments, 'comments') };
}

/** Whether pack-review wrote the comment: the token's identity wrote it, and it ends with the marker. */
export function own(comment: { readonly viewerDidAuthor: boolean; readonly body: string }): boolean {
  return comment.viewerDidAuthor && comment.body.trimEnd().endsWith(MARKER);
}

/** A comment as pack-review posts it: marked as Claude's for people, and as pack-review's for the next run. */
export function signed(body: string): string {
  return `🤖 ${body}\n\n${MARKER}`;
}
