import json

from review_case import HEAD, ReviewCase

BASE = 'b' * 40
NUMBERS = {'file': 'AGENTS.md', 'quote': 'Game numbers live in content.', 'routed': True}
SIM = {'file': 'docs/sim.md', 'quote': 'Sim code reads its numbers from content.', 'routed': False}


def source(id, rules=(), spots=(), deliberate=(), exemplars=(), kind='deviation'):
    """One finder's finding as sources.json numbers it."""
    return {'id': id, 'finding': {'kind': kind, 'headline': f'Finder headline {id}', 'rules': list(rules),
                                  'spots': list(spots), 'deliberate': list(deliberate),
                                  'exemplars': list(exemplars), 'take': f'Finder take {id}.'}}


def spot(path, line, follows=False):
    return {'path': path, 'line': line, 'follows': follows}


def group(*ids, kind='deviation', headline='A game number in sim code', take='Move it to content.'):
    return {'ids': list(ids), 'kind': kind, 'headline': headline, 'take': take}


class ReportCase(ReviewCase):
    """The merge job after its agent: the finders' findings as sources.json numbers them, and the agent's groups."""

    def report(self, sources, groups, shown=None):
        (self.root / 'sources.json').write_text(json.dumps(sources))
        (self.root / 'groups.json').write_text(groups if isinstance(groups, str) else json.dumps({'groups': groups}))
        (self.root / 'shown.json').write_text(json.dumps(shown or {}))
        return self.script('report', '--base', BASE, '--base-ref', 'main', '--head', HEAD, '--sources', 'sources.json',
                           '--groups', 'groups.json', '--shown', 'shown.json', '--out', 'report.json')

    def findings(self, sources, groups):
        run = self.report(sources, groups)
        self.assertEqual(run.returncode, 0, run.stderr)
        return json.loads((self.root / 'report.json').read_text())['findings']


class BuildTests(ReportCase):
    """Each finding is built from the finders' findings its group names, so the merge can't drop what they found."""

    def test_builds_a_finding_from_every_source_its_group_names(self):
        sources = [source('0:0', rules=[NUMBERS], spots=[spot('src/sim.ts', 42)], deliberate=['Commit abc says so.']),
                   source('2:1', rules=[SIM, NUMBERS], spots=[spot('src/sim.ts', 42), spot('src/rng.ts', 9)],
                          deliberate=['Commit abc says so.', 'A comment at the spot.'])]

        [finding] = self.findings(sources, [group('0:0', '2:1')])

        self.assertEqual(finding, {
            'kind': 'deviation', 'headline': 'A game number in sim code', 'take': 'Move it to content.',
            'rules': [NUMBERS, SIM], 'spots': [spot('src/sim.ts', 42), spot('src/rng.ts', 9)],
            'deliberate': ['Commit abc says so.', 'A comment at the spot.'], 'exemplars': []})

    def test_counts_a_spot_as_deviating_when_any_source_says_it_deviates(self):
        sources = [source('0:0', rules=[NUMBERS], spots=[spot('src/sim.ts', 42)]),
                   source('1:0', rules=[SIM], spots=[spot('src/sim.ts', 42, follows=True)])]

        [finding] = self.findings(sources, [group('0:0', '1:0', kind='conflict')])

        self.assertEqual(finding['kind'], 'conflict')
        self.assertEqual(finding['spots'], [spot('src/sim.ts', 42)])

    def test_keeps_an_uncovered_choices_exemplars_in_the_finding_that_holds_it(self):
        ways = [{'way': 'Loaded at startup', 'examples': ['src/load.ts:8']}]
        sources = [source('0:0', rules=[NUMBERS], spots=[spot('src/load.ts', 3)]),
                   source('3:0', kind='uncovered choice', spots=[spot('src/load.ts', 3)], exemplars=ways)]

        [finding] = self.findings(sources, [group('0:0', '3:0')])

        self.assertEqual(finding['exemplars'], ways)
        self.assertEqual(finding['rules'], [NUMBERS])

    def test_keeps_the_groups_in_the_order_the_agent_gave_them(self):
        sources = [source('0:0'), source('1:0')]

        findings = self.findings(sources, [group('1:0', headline='Second'), group('0:0', headline='First')])

        self.assertEqual([f['headline'] for f in findings], ['Second', 'First'])


class CheckTests(ReportCase):
    """A merge that would drop, repeat or invent a finder's finding stops the run before anything is posted."""

    def test_refuses_groups_that_leave_out_repeat_or_invent_a_finders_finding(self):
        sources = [source('0:0'), source('1:0')]
        for groups, says in (([group('0:0')], 'leave out 1:0'),
                             ([group('0:0', '1:0'), group('1:0')], 'put 1:0 in more than one group'),
                             ([group('0:0', '1:0', '9:9')], 'name 9:9, which no finder reported')):
            with self.subTest(says=says):
                run = self.report(sources, groups)

                self.assertEqual(run.returncode, 1)
                self.assertIn(says, run.stderr)
                self.assertFalse((self.root / 'report.json').exists())

    def test_refuses_an_answer_that_isnt_groups(self):
        run = self.report([source('0:0')], '{"findings": []}')

        self.assertEqual(run.returncode, 1)
        self.assertIn('returned no groups', run.stderr)
