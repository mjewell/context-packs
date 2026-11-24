/**
 * What of a PR's review threads an agent may read. A comment's text comes back only when its author can write to the
 * repo now, or pack-review wrote it. Anyone else's comment comes back as its id and why it's hidden, without their
 * login, which is text they chose. The pairing job reads threads only through this module, so the rule has one home.
 */
import * as github from './github.ts';
import { clean } from './sanitize.ts';

const PAGE = 100;
const FIELDS = 'id author { login __typename } createdAt body bodyText viewerDidAuthor isMinimized minimizedReason';
const LIST = `pageInfo { hasNextPage endCursor } nodes { ${FIELDS} }`;
const THREADS = `query Threads($owner: String!, $name: String!, $number: Int!, $after: String) {
  repository(owner: $owner, name: $name) { pullRequest(number: $number) {
    reviewThreads(first: ${PAGE}, after: $after) { pageInfo { hasNextPage endCursor }
      nodes { id path line isResolved comments(first: ${PAGE}) { ${LIST} } } } } } }`;
const THREAD_COMMENTS = `query ThreadComments($id: ID!, $after: String) {
  node(id: $id) { ... on PullRequestReviewThread { comments(first: ${PAGE}, after: $after) { ${LIST} } } } }`;
// GitHub's roles that can push.
const WRITERS = new Set(['write', 'maintain', 'admin']);

interface Node {
  readonly id: string;
  readonly author: { readonly login: string; readonly __typename: string } | null;
  readonly createdAt: string;
  readonly body: string;
  readonly bodyText: string;
  readonly viewerDidAuthor: boolean;
  readonly isMinimized: boolean;
  readonly minimizedReason: string | null;
}

interface Page<T> {
  readonly pageInfo: { readonly hasNextPage: boolean; readonly endCursor: string | null };
  readonly nodes: T[];
}

/** A comment as an agent may see it: hidden, with why, or shown, with its text. */
export type Shown =
  | { readonly id: string; readonly hidden: string }
  | {
      readonly id: string;
      readonly author: string;
      readonly at: string;
      readonly text: string;
      readonly ours: boolean;
      readonly minimized?: string | null;
    };

export interface Thread {
  readonly id: string;
  readonly path: string;
  readonly line: number | null;
  readonly resolved: boolean;
  readonly comments: Shown[];
}

/** Every item of a list from after on, reading each page in turn. field finds the list in an answer. */
async function every<T>(
  operation: string,
  query: string,
  variables: Record<string, unknown>,
  field: (data: any) => Page<T>,
  after: string | null = null,
): Promise<T[]> {
  const items: T[] = [];
  for (;;) {
    const page = field(await github.graphql(operation, query, { ...variables, after }));
    items.push(...page.nodes);
    if (!page.pageInfo.hasNextPage) return items;
    after = page.pageInfo.endCursor;
  }
}

/** login escaped for a URL path, as urllib.parse.quote(login, safe='') escapes it. */
function quoted(login: string): string {
  return encodeURIComponent(login).replace(/[!'()*]/g, (c) => `%${c.charCodeAt(0).toString(16).toUpperCase()}`);
}

/** Who can write to the repo now, asked of GitHub once per author. */
class Access {
  readonly #known = new Map<string, boolean>();
  readonly owner: string;
  readonly name: string;

  constructor(owner: string, name: string) {
    this.owner = owner;
    this.name = name;
  }

  async writes(login: string): Promise<boolean> {
    if (!this.#known.has(login)) {
      try {
        const answer = await github.rest(`/repos/${this.owner}/${this.name}/collaborators/${quoted(login)}/permission`);
        this.#known.set(login, WRITERS.has(answer.role_name));
      } catch (error) {
        // GitHub answers 404 for someone who isn't a collaborator. Any other refusal stops the run.
        if (!(error instanceof github.GitHubError) || error.code !== 404) throw error;
        this.#known.set(login, false);
      }
    }
    return this.#known.get(login)!;
  }
}

/** The comment as the agent may see it. */
async function shown(node: Node, access: Access): Promise<Shown> {
  const author = node.author;
  let why: string | null = null;
  if (github.own(node)) why = null;
  else if (author !== null && author.__typename === 'Bot') why = 'written by a bot';
  else if (author === null || !(await access.writes(author.login))) why = 'author lacks write access';
  if (why) return { id: node.id, hidden: why };
  // ours lets the commentary agent tell its own earlier replies from people's, so it doesn't repeat itself.
  const seen = {
    id: node.id,
    author: author!.login,
    at: node.createdAt,
    text: clean(node.bodyText),
    ours: github.own(node),
  };
  // A minimized comment still comes through, since only pack-review and people who can write get this far. GitHub's
  // reason, such as outdated, tells the commentary agent whether it still applies.
  return node.isMinimized ? { ...seen, minimized: node.minimizedReason } : seen;
}

/** pack-review's review threads on the PR, open and resolved, each with every comment in it as the agent may see it. */
export async function threads(number: number): Promise<Thread[]> {
  const [owner, name] = github.repository();
  const access = new Access(owner, name);
  const found: Thread[] = [];
  const listed = await every<{
    id: string;
    path: string;
    line: number | null;
    isResolved: boolean;
    comments: Page<Node>;
  }>('Threads', THREADS, { owner, name, number }, (data) => data.repository.pullRequest.reviewThreads);
  for (const thread of listed) {
    const first = thread.comments;
    const comments = [...first.nodes];
    if (first.pageInfo.hasNextPage) {
      comments.push(
        ...(await every<Node>(
          'ThreadComments',
          THREAD_COMMENTS,
          { id: thread.id },
          (data) => data.node.comments,
          first.pageInfo.endCursor,
        )),
      );
    }
    if (!comments.length || !github.own(comments[0]!)) continue;
    const seen: Shown[] = [];
    for (const node of comments) seen.push(await shown(node, access));
    found.push({
      id: thread.id,
      path: clean(thread.path),
      line: thread.line,
      resolved: thread.isResolved,
      comments: seen,
    });
  }
  return found;
}
