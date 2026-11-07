"""Stands in for GitHub's GraphQL API in tests: an HTTP server on a free local port that answers each request with the
raw response its test set, keyed by the operation's name, and records every request it gets."""
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


def comment(body, mine=False, id='IC_1'):
    """A comment as the PullRequest query returns it. mine is whether the token's identity wrote it."""
    return {'id': id, 'viewerDidAuthor': mine, 'body': body}


def pull_request(comments=(), more=False, head='h' * 40):
    """The PullRequest query's response. more is whether its comments have another page."""
    return ok({'repository': {'pullRequest': {
        'id': 'PR_1', 'headRefOid': head, 'comments': connection(list(comments), more)}}})
