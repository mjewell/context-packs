import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from fake_github import FakeGitHub, comment

REVIEW = Path(__file__).resolve().parents[1] / 'review'
MARKER = '<!-- pack-review -->'
HEAD = 'h' * 40


def own(body, id='IC_1'):
    """A comment pack-review posted earlier."""
    return comment(f'🤖 {body}\n\n{MARKER}', login='github-actions', association='NONE', mine=True, id=id)


class ReviewCase(unittest.TestCase):
    """A PR, number 7 in o/r, on a fake GitHub, and a folder for the files the review scripts read and write."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='context-packs-review-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.github = FakeGitHub()
        self.addCleanup(self.github.stop)
        self.env = {**os.environ, 'GITHUB_TOKEN': 'token-1', 'GITHUB_REPOSITORY': 'o/r',
                    'GITHUB_API_URL': self.github.url, 'GITHUB_GRAPHQL_URL': f'{self.github.url}/graphql'}

    def script(self, name, *args):
        return subprocess.run([sys.executable, str(REVIEW / f'{name}.py'), *map(str, args)], cwd=self.root,
                              env=self.env, capture_output=True, text=True)

    def sent(self, operation):
        """What each request for the operation sent: a GraphQL operation's variables, or a REST request's body."""
        return [request.get('variables', request.get('body')) for request in self.github.requests
                if request['operationName'] == operation]


class Mcp:
    """A client for the review's MCP server, speaking JSON-RPC over its stdin and stdout as Claude Code does."""

    def __init__(self, case, *args):
        self.process = subprocess.Popen([sys.executable, str(REVIEW / 'tools.py'), *map(str, args)], cwd=case.root,
                                        env=case.env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, text=True)
        case.addCleanup(self.close)
        self.next = 0

    def send(self, method, params=None, notify=False):
        message = {'jsonrpc': '2.0', 'method': method, **({'params': params} if params is not None else {})}
        if not notify:
            self.next += 1
            message['id'] = self.next
        self.process.stdin.write(json.dumps(message) + '\n')
        self.process.stdin.flush()
        if notify:
            return None
        answer = json.loads(self.process.stdout.readline())
        assert answer['id'] == self.next, answer
        return answer

    def start(self):
        answer = self.send('initialize', {'protocolVersion': '2025-06-18', 'capabilities': {},
                                          'clientInfo': {'name': 'test', 'version': '1'}})
        self.send('notifications/initialized', notify=True)
        return answer

    def call(self, name, **arguments):
        """The tool's result: its text, and whether it's an error."""
        result = self.send('tools/call', {'name': name, 'arguments': arguments})['result']
        [content] = result['content']
        return content['text'], result.get('isError', False)

    def close(self):
        self.process.stdin.close()
        self.process.wait(5)
        self.process.stdout.close()
        self.process.stderr.close()
