import json

from review_case import HEAD, ReviewCase

BASE = 'b' * 40
NUMBERS = {'file': 'AGENTS.md', 'quote': 'Game numbers live in content.', 'routed': True}


def source(id, rules=(), spots=(), kind='deviation'):
    """One finder's finding, with its id."""
    return {'id': id, 'finding': {'kind': kind, 'headline': f'Finder headline {id}', 'rules': list(rules),
                                  'spots': list(spots), 'deliberate': [], 'exemplars': [],
                                  'take': f'Finder take {id}.'}}


def spot(path, line, follows=False):
    return {'path': path, 'line': line, 'follows': follows}


class ReportCase(ReviewCase):
    """The review job after its agent: the findings the wizard built, and the head lines each diff shows."""


class FindingsTests(ReportCase):
    """A review that ran the wizard already built its findings, so the report starts from them: it adds the base
    branch and the line each finding's thread opens on, and refuses findings for another head."""

    def from_findings(self, findings, head=HEAD, shown=None):
        (self.root / 'findings.json').write_text(json.dumps({'base': BASE, 'head': head, 'findings': findings}))
        (self.root / 'shown.json').write_text(json.dumps(shown or {}))
        return self.script('report', '--base', BASE, '--base-ref', 'main', '--head', HEAD, '--findings',
                           'findings.json', '--shown', 'shown.json', '--out', 'report.json')

    def test_reports_the_wizards_findings_with_their_anchors(self):
        found = source('0:0', rules=[NUMBERS], spots=[spot('src/sim.ts', 42)])['finding']

        run = self.from_findings([found], shown={'src/sim.ts': [41, 42]})

        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads((self.root / 'report.json').read_text()), {
            'base': BASE, 'base_ref': 'main', 'head': HEAD, 'findings': [found],
            'anchors': [{'path': 'src/sim.ts', 'line': 42}]})

    def test_cleans_the_findings_text_like_the_merges(self):
        found = {**source('0:0')['finding'], 'headline': 'A zero​width space'}

        self.assertEqual(self.from_findings([found]).returncode, 0)

        [reported] = json.loads((self.root / 'report.json').read_text())['findings']
        self.assertEqual(reported['headline'], 'A zerowidth space')

    def test_refuses_findings_for_another_head(self):
        run = self.from_findings([], head='x' * 40)

        self.assertEqual(run.returncode, 1)
        self.assertIn(f"pack-review: the review's findings are for {'x' * 40}, not the head, {HEAD}.", run.stderr)
        self.assertFalse((self.root / 'report.json').exists())
