from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ModuleNameTests(unittest.TestCase):
    """review/ and src/ share one set of module names. The wizard puts src/ first on the import path, and the CLI puts
    review/ first for `review`, so a module name in both folders makes each import whichever comes first, silently.
    src/report.py once shadowed review/report.py this way."""

    def test_no_module_name_is_in_both_review_and_src(self):
        review = {path.stem for path in (ROOT / 'review').glob('*.py')}
        src = {path.stem for path in (ROOT / 'src').glob('*.py')}

        self.assertEqual(review & src, set(), 'rename one of these, since the other folder has a module of that name')
