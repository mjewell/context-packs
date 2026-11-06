import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from fake_github import FakeGitHub

REVIEW = Path(__file__).resolve().parents[1] / 'review'


class ReviewCase(unittest.TestCase):
    """A PR in o/r on a fake GitHub, and a folder for the files the review scripts read and write."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='context-packs-review-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.github = FakeGitHub()
        self.addCleanup(self.github.stop)
        self.env = {**os.environ, 'GITHUB_TOKEN': 'token-1', 'GITHUB_REPOSITORY': 'o/r',
                    'GITHUB_GRAPHQL_URL': self.github.url}

    def script(self, name, *args):
        return subprocess.run([sys.executable, str(REVIEW / f'{name}.py'), *map(str, args)], cwd=self.root,
                              env=self.env, capture_output=True, text=True)
