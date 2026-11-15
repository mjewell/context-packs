"""Stands in for GitHub's API in tests: an HTTP server on a free local port that answers each request with the raw
response its test set, keyed by the GraphQL operation's name or the REST path, and records every request it gets."""
import http.server
import json
import threading


class FakeGitHub:
    def __init__(self):
        self.responses = {}
        self.rest = {}
        self.requests = []
        fake = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                assert self.path == '/graphql', self.path
                fake.requests.append({'authorization': self.headers.get('Authorization'), **request})
                response = fake.responses[request['operationName']]
                status, answer = response(request['variables']) if callable(response) else response
                body = json.dumps(answer).encode()
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                fake.requests.append({'authorization': self.headers.get('Authorization'), 'path': self.path})
                status, answer = fake.rest.get(self.path, (404, {'message': 'Not Found'}))
                body = json.dumps(answer).encode()
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=self.server.serve_forever, args=(0.05,), daemon=True).start()

    @property
    def url(self):
        return f'http://127.0.0.1:{self.server.server_address[1]}'

    def stop(self):
        self.server.shutdown()
        self.server.server_close()

    def operations(self):
        return [request['operationName'] for request in self.requests if 'operationName' in request]

    def writes(self):
        return [name for name in self.operations() if name != 'PullRequest']


def ok(data):
    return 200, {'data': data}


def connection(nodes, more=False, end=None):
    """A list's page, as GitHub returns one. end is the cursor for the page after it."""
    return {'pageInfo': {'hasNextPage': more, 'endCursor': end}, 'nodes': nodes}


def comment(body, mine=False, id='IC_1'):
    """A comment as the PullRequest query returns it. mine is whether the token's identity wrote it."""
    return {'id': id, 'viewerDidAuthor': mine, 'body': body}


def pull_request(comments=(), more=False, head='h' * 40, base_ref='main'):
    """The PullRequest query's response. more is whether its comments have another page."""
    return ok({'repository': {'pullRequest': {
        'id': 'PR_1', 'headRefOid': head, 'baseRefName': base_ref, 'comments': connection(list(comments), more)}}})


def said(text, author='alice', id='C_1', body=None, mine=False, minimized=False, bot=False,
         at='2026-11-01T10:00:00Z'):
    """A comment or review as GitHub's GraphQL API returns one: text is its bodyText, and body its Markdown, the same
    unless given. author None is a deleted account, which GitHub returns as no author."""
    return {'id': id, 'author': None if author is None else {'login': author, '__typename': 'Bot' if bot else 'User'},
            'createdAt': at, 'body': text if body is None else body, 'bodyText': text, 'viewerDidAuthor': mine,
            'isMinimized': minimized}


def thread(id, comments, path='src/a.py', line=3, resolved=False, more=False, end=None):
    """A review thread as GitHub's GraphQL API returns one, with its first page of comments."""
    return {'id': id, 'path': path, 'line': line, 'isResolved': resolved,
            'comments': connection(list(comments), more, end)}


def role(name):
    """The REST answer to whether a user can push: GitHub's role_name, and the older permission it maps to."""
    old = {'admin': 'admin', 'maintain': 'write', 'write': 'write', 'triage': 'read', 'read': 'read'}[name]
    return 200, {'permission': old, 'role_name': name, 'user': {'login': 'someone'}}
