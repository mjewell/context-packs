"""The repo and runs the wizard's tests share: a change against two packs' tables, and helpers that run its steps
as an agent would."""
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
import tempfile

from git_case import REVIEW, GitCase

ROOT = REVIEW.parent

# The block as a sync writes it, so the CLI's check that it wasn't edited passes.
BODY = '''## Context

| When | Read |
|---|---|
| Writing tests | `docs/testing.md` |
| Committing | `docs/git.md` |

## style context

| When | Read |
|---|---|
| Writing prose | `docs/prose.md` |
'''
AGENTS = ('# Repo\n\n<!-- context-packs:start -->\n' + BODY
          + f'<!-- context-packs:end sha256:{hashlib.sha256(BODY.encode()).hexdigest()[:12]} -->\n')
DOCS = {'docs/testing.md': '# Testing\n\nTest behavior.\n', 'docs/git.md': '# Git\n\nSmall commits.\n',
        'docs/prose.md': '# Prose\n\nShort sentences.\n'}


class WizardCase(GitCase):
    """A repo whose instruction file has two packs' tables, so the review has two pack units after the instruction
    file's, and a change on top of its base that edits one file and adds another. The wizard runs in it the way an
    agent runs it, as a command."""

    def setUp(self):
        super().setUp()
        self.commit('Add the packs and the app', {'AGENTS.md': AGENTS, **DOCS, 'src/app.py': 'x = 1\n'})
        self.base = self.git('rev-parse', 'HEAD')
        self.head = self.commit('Change the app', {'src/app.py': 'x = 2\n', 'tests/test_app.py': 'assert True\n'})
        temp = tempfile.TemporaryDirectory(prefix='context-packs-runs-')
        self.addCleanup(temp.cleanup)
        self.env = {**{key: value for key, value in os.environ.items() if not key.startswith('GIT_')},
                    'TMPDIR': temp.name}
        self.run_dir = None

    def wizard(self, *args, input=''):
        return subprocess.run([sys.executable, str(REVIEW / 'wizard.py'), *args], cwd=self.repo, env=self.env,
                              input=input, capture_output=True, text=True)

    def init(self):
        """What init printed, once it succeeded. The run folder it made is in every command it prints."""
        run = self.wizard('init', '--base', self.base, '--head', 'HEAD', '--command', 'review')
        self.assertEqual(run.returncode, 0, run.stderr)
        self.run_dir = re.search(r'review --run (\S+) ', run.stdout).group(1)
        return run.stdout

    def command(self, *args):
        """A command as the wizard prints it for this run."""
        return ' '.join(['review', '--run', self.run_dir, *args])

    def answer_path(self, name):
        """Where an agent writes one of this run's answers, such as unit-1.json."""
        return Path(self.env['TMPDIR']) / 'pack-review-answers' / Path(self.run_dir).name / name


class StartedCase(WizardCase):
    """A run init started."""

    def setUp(self):
        super().setUp()
        self.init()

    def step(self, *args):
        """A step of this run: what it printed, and what it printed as an error, with its exit code."""
        return self.wizard('--run', self.run_dir, *args)

    def submit_groups(self, groups):
        """The merging agent's groups, written where its brief says, then submitted."""
        self.answer_path('groups.json').write_text(json.dumps({'groups': groups}))
        return self.step('submit-groups')


def deviation(headline='Tests reach into a private helper', path='tests/test_app.py', line=1):
    return {'kind': 'deviation', 'headline': headline,
            'rules': [{'file': 'docs/testing.md', 'quote': 'Test behavior.', 'routed': True}],
            'spots': [{'path': path, 'line': line, 'follows': False}], 'deliberate': [], 'exemplars': [],
            'take': 'Test through the public interface.'}


class SubmitCase(StartedCase):
    """A finder at the end of its brief: it read its docs, writes its answer where the brief says, and submits it."""

    def submit(self, finder, findings):
        text = findings if isinstance(findings, str) else json.dumps({'findings': findings})
        self.answer_path(f'unit-{finder}.json').write_text(text)
        return self.step('submit', str(finder))

    def read_docs(self, unit, count):
        for n in range(1, count + 1):
            run = self.step('doc', str(unit), str(n))
            self.assertEqual(run.returncode, 0, run.stderr)

    def submit_unit(self, unit, docs, findings):
        self.read_docs(unit, docs)
        run = self.submit(unit, findings)
        self.assertEqual(run.returncode, 0, run.stderr)
