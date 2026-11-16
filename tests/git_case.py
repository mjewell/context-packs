import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

REVIEW = Path(__file__).resolve().parents[1] / 'review'


class GitCase(unittest.TestCase):
    """A git repo in a temporary folder, with a base commit and commits on top of it, and the review's git server
    started in it the way the review action starts it."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='context-packs-git-')
        self.addCleanup(temp.cleanup)
        self.repo = Path(temp.name)
        self.git('init', '-q', '-b', 'main')
        self.git('config', 'user.name', 'Test')
        self.git('config', 'user.email', 'test@example.com')
        self.git('commit', '-q', '--allow-empty', '-m', 'Start')
        self.base = self.git('rev-parse', 'HEAD')

    def git(self, *args):
        return subprocess.run(['git', *args], cwd=self.repo, capture_output=True, text=True,
                              check=True).stdout.strip()

    def commit(self, message, files=(), removed=()):
        """A commit on top of the last that writes each of files, a {path: text} dict, and deletes each of removed.
        Its hash."""
        for path, text in dict(files).items():
            (self.repo / path).parent.mkdir(parents=True, exist_ok=True)
            (self.repo / path).write_text(text)
            self.git('add', '--', path)
        for path in removed:
            self.git('rm', '-q', '--', path)
        self.git('commit', '-q', '-m', message)
        return self.git('rev-parse', 'HEAD')

    def server(self):
        """The git server, started for the change from the base to the last commit, initialized and ready."""
        return Server(self.repo, self.base, self.git('rev-parse', 'HEAD'), self)


class Server:
    """A client for the git server over stdio, which sends one request at a time and reads its answer."""

    def __init__(self, repo, base, head, case):
        self.process = subprocess.Popen(
            [sys.executable, str(REVIEW / 'git_server.py'), '--base', base, '--head', head], cwd=repo,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            env={key: value for key, value in os.environ.items() if not key.startswith('GIT_')})
        case.addCleanup(self.stop)
        self.next = 0
        self.initialized = self.request('initialize', {'protocolVersion': '2025-06-18', 'capabilities': {},
                                                       'clientInfo': {'name': 'test', 'version': '1'}})
        self.send({'jsonrpc': '2.0', 'method': 'notifications/initialized'})

    def send(self, message):
        self.process.stdin.write(json.dumps(message) + '\n')
        self.process.stdin.flush()

    def request(self, method, params=None):
        """The answer to one request: its result, or its error."""
        self.next += 1
        self.send({'jsonrpc': '2.0', 'id': self.next, 'method': method, **({'params': params} if params else {})})
        line = self.process.stdout.readline()
        if not line:
            raise AssertionError(f'the server stopped: {self.process.stderr.read()}')
        answer = json.loads(line)
        assert answer['id'] == self.next, answer
        return answer.get('result', answer.get('error'))

    def call(self, tool, **arguments):
        """The text a tool returned, and whether it was an error."""
        result = self.request('tools/call', {'name': tool, 'arguments': arguments})
        [content] = result['content']
        return content['text'], result.get('isError', False)

    def text(self, tool, **arguments):
        """The text a tool returned, which must not be an error."""
        text, error = self.call(tool, **arguments)
        assert not error, text
        return text

    def stop(self):
        self.process.stdin.close()
        self.process.wait(timeout=10)
        self.process.stdout.close()
        self.process.stderr.close()
