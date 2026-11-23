from pathlib import Path
import subprocess
import tempfile
import unittest

REVIEW = Path(__file__).resolve().parents[1] / 'review'


class GitCase(unittest.TestCase):
    """A git repo in a temporary folder, with a base commit and commits on top of it."""

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
