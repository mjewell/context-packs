"""Stands in for GitHub's API in tests: an HTTP server on a free local port that answers each request with the raw
response its test set, keyed by the GraphQL operation's name or by a REST request's method and path, and records every
request it gets."""
import http.server
import json
import threading


class FakeGitHub:
    def __init__(self):
        self.responses = {}
        self.requests = []
        fake = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                if self.path == '/graphql':
                    key, recorded = request['operationName'], request
                    argument = request['variables']
                else:
                    key, recorded = f'POST {self.path}', {'operationName': f'POST {self.path}', 'body': request}
                    argument = request
                fake.requests.append({'authorization': self.headers.get('Authorization'), **recorded})
                response = fake.responses[key]
                status, answer = response(argument) if callable(response) else response
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
        return [request['operationName'] for request in self.requests]

    def writes(self):
        return [name for name in self.operations() if name != 'PullRequest']


def ok(data):
    return 200, {'data': data}


def connection(nodes, more=False):
    return {'pageInfo': {'hasNextPage': more}, 'nodes': nodes}


def comment(body, login='alice', association='MEMBER', mine=False, id='IC_1'):
    """A comment as GitHub's GraphQL API returns it. mine is whether the token's identity wrote it."""
    return {'id': id, 'author': {'login': login}, 'authorAssociation': association, 'viewerDidAuthor': mine,
            'body': body}


def review(body, login='alice', association='MEMBER', state='COMMENTED', mine=False):
    return {'author': {'login': login}, 'authorAssociation': association, 'viewerDidAuthor': mine, 'state': state,
            'body': body}


def thread(comments, id='PRRT_1', path='src/app.ts', line=12, resolved=False, outdated=False, more=False):
    return {'id': id, 'isResolved': resolved, 'isOutdated': outdated, 'path': path, 'line': line,
            'comments': connection(comments, more)}


def pull_request(title='Add refunds', body='Adds a refund endpoint.', login='alice', association='MEMBER',
                 comments=(), reviews=(), threads=(), more=(), head='h' * 40):
    """The PullRequest query's response. more names the lists that have another page."""
    return ok({'repository': {'pullRequest': {
        'id': 'PR_1', 'title': title, 'body': body, 'author': {'login': login}, 'authorAssociation': association,
        'baseRefOid': 'b' * 40, 'headRefOid': head,
        'comments': connection(list(comments), 'comments' in more),
        'reviews': connection(list(reviews), 'reviews' in more),
        'reviewThreads': connection(list(threads), 'reviewThreads' in more),
    }}})
