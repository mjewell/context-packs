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
    return comment(f'🤖 {body}\n\n{MARKER}', mine=True, id=id)


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

    def script(self, name, *args, input=None):
        return subprocess.run([sys.executable, str(REVIEW / f'{name}.py'), *map(str, args)], cwd=self.root,
                              env=self.env, input=input, capture_output=True, text=True)

    def sent(self, operation):
        """The variables each request for the operation sent."""
        return [request['variables'] for request in self.github.requests
                if request['operationName'] == operation]

