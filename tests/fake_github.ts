/**
 * Stands in for GitHub's API in tests: an HTTP server on a free local port that answers each request with the raw
 * response its test set, keyed by the GraphQL operation's name or the REST path, and records every request it gets.
 */
import http from 'node:http';
import type { AddressInfo } from 'node:net';
import type { TestContext } from 'node:test';

/** An HTTP status and the JSON body to answer with. */
export type Answer = readonly [number, unknown];
type Variables = Record<string, unknown>;

export interface Request {
  readonly authorization: string | undefined;
  readonly operationName?: string;
  readonly query?: string;
  readonly variables?: Variables;
  readonly path?: string;
}

/** The fake PR's head and base commits. */
export const HEAD = 'h'.repeat(40);
export const BASE = 'b'.repeat(40);

export class FakeGitHub {
  readonly responses: Record<string, Answer | ((variables: Variables) => Answer)> = {};
  readonly rest: Record<string, Answer> = {};
  readonly requests: Request[] = [];
  readonly #server: http.Server;

  private constructor(server: http.Server) {
    this.#server = server;
  }

  /** A fake GitHub listening on a free port, closed when the test ends. */
  static async start(t: TestContext): Promise<FakeGitHub> {
    const fake: FakeGitHub = new FakeGitHub(http.createServer((request, response) => fake.#answer(request, response)));
    await new Promise<void>((resolve) => fake.#server.listen(0, '127.0.0.1', resolve));
    t.after(() => new Promise<void>((resolve) => fake.#server.close(() => resolve())));
    return fake;
  }

  get url(): string {
    return `http://127.0.0.1:${(this.#server.address() as AddressInfo).port}`;
  }

  operations(): string[] {
    return this.requests.flatMap((request) => (request.operationName ? [request.operationName] : []));
  }

  /** The GraphQL mutations it was sent, by name. */
  writes(): string[] {
    return this.requests
      .filter((request) => (request.query ?? '').trimStart().startsWith('mutation'))
      .map((request) => request.operationName!);
  }

  #answer(request: http.IncomingMessage, response: http.ServerResponse): void {
    const authorization = request.headers.authorization;
    let body = '';
    request.setEncoding('utf8').on('data', (chunk: string) => {
      body += chunk;
    });
    request.on('end', () => {
      let answer: Answer;
      if (request.method === 'POST') {
        const sent = JSON.parse(body) as { operationName: string; query: string; variables: Variables };
        this.requests.push({ authorization, ...sent });
        const set = request.url === '/graphql' ? this.responses[sent.operationName] : undefined;
        // A request the test set no answer for fails the script with a 500, rather than looking like an empty answer.
        answer =
          set === undefined
            ? [500, { message: `the fake has no answer for ${request.url} ${sent.operationName}` }]
            : typeof set === 'function'
              ? set(sent.variables)
              : set;
      } else {
        this.requests.push({ authorization, path: request.url! });
        answer = this.rest[request.url!] ?? [404, { message: 'Not Found' }];
      }
      const [status, json] = answer;
      const text = JSON.stringify(json);
      response.writeHead(status, { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(text) });
      response.end(text);
    });
  }
}

export function ok(data: unknown): Answer {
  return [200, { data }];
}

/** A list's page, as GitHub returns one. end is the cursor for the page after it. */
export function connection(nodes: readonly unknown[], more = false, end: string | null = null) {
  return { pageInfo: { hasNextPage: more, endCursor: end }, nodes: [...nodes] };
}

/** A comment as the PullRequest query returns it. mine is whether the token's identity wrote it. */
export function comment(body: string, { mine = false, id = 'IC_1' } = {}) {
  return { id, viewerDidAuthor: mine, body };
}

/** The PullRequest query's response. more is whether its comments have another page. */
export function pullRequest({
  comments = [] as readonly unknown[],
  more = false,
  head = HEAD,
  baseRef = 'main',
} = {}): Answer {
  return ok({
    repository: {
      pullRequest: { id: 'PR_1', headRefOid: head, baseRefName: baseRef, comments: connection(comments, more) },
    },
  });
}

/**
 * A review comment as GitHub's GraphQL API returns one: text is its bodyText, and body its Markdown, the same unless
 * given. author null is a deleted account, which GitHub returns as no author. minimized is the reason a maintainer
 * gave for minimizing it, such as 'outdated', or null.
 */
export function said(
  text: string,
  {
    author = 'alice' as string | null,
    id = 'C_1',
    body = undefined as string | undefined,
    mine = false,
    minimized = null as string | null,
    bot = false,
    at = '2026-11-01T10:00:00Z',
  } = {},
) {
  return {
    id,
    author: author === null ? null : { login: author, __typename: bot ? 'Bot' : 'User' },
    createdAt: at,
    body: body ?? text,
    bodyText: text,
    viewerDidAuthor: mine,
    isMinimized: minimized !== null,
    minimizedReason: minimized,
  };
}

/** A review thread as GitHub's GraphQL API returns one, with its first page of comments. */
export function thread(
  id: string,
  comments: readonly unknown[],
  { path = 'src/a.py', line = 3 as number | null, resolved = false, more = false, end = null as string | null } = {},
) {
  return { id, path, line, isResolved: resolved, comments: connection(comments, more, end) };
}

const ROLES: Readonly<Record<string, string>> = {
  admin: 'admin',
  maintain: 'write',
  write: 'write',
  triage: 'read',
  read: 'read',
};

/** The REST answer to whether a user can push: GitHub's role_name, and the older permission it maps to. */
export function role(name: string): Answer {
  return [200, { permission: ROLES[name], role_name: name, user: { login: 'someone' } }];
}
