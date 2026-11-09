import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from review_case import REVIEW

BLOCK = '<!-- context-packs:start -->\n<!-- context-packs:end sha256:x -->\n'


class UnitsTests(unittest.TestCase):
    """The units the review checks in parallel: the instruction file's own rules, then each pack's docs, as the matrix
    the review workflow's unit jobs run over."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='context-packs-units-')
        self.addCleanup(temp.cleanup)
        self.repo = Path(temp.name)

    def units(self, docs):
        run = subprocess.run([sys.executable, str(REVIEW / 'units.py')], cwd=self.repo, input=docs,
                             capture_output=True, text=True)
        return run

    def matrix(self, docs):
        run = self.units(docs)
        self.assertEqual(run.returncode, 0, run.stderr)
        name, value = run.stdout.rstrip('\n').split('=', 1)
        self.assertEqual(name, 'matrix')
        return json.loads(value)

    def test_checks_the_instruction_file_then_each_pack(self):
        (self.repo / 'AGENTS.md').write_text(f'# Rules\n\n{BLOCK}')

        matrix = self.matrix('context-packs/game/a.md\ncontext-packs/game/b.md\n\ncontext-packs/gen/core/c.md\n')

        self.assertEqual(matrix, {'include': [{'unit': 1, 'docs': ['AGENTS.md']},
                                              {'unit': 2, 'docs': ['context-packs/game/a.md', 'context-packs/game/b.md']},
                                              {'unit': 3, 'docs': ['context-packs/gen/core/c.md']}]})

    def test_uses_claude_md_when_it_holds_the_rules(self):
        (self.repo / 'CLAUDE.md').write_text(BLOCK)

        self.assertEqual(self.matrix('')['include'], [{'unit': 1, 'docs': ['CLAUDE.md']}])

    def test_stops_when_the_repo_has_no_instruction_file(self):
        run = self.units('')

        self.assertNotEqual(run.returncode, 0)
        self.assertIn('no AGENTS.md or CLAUDE.md', run.stderr)


if __name__ == '__main__':
    unittest.main()
