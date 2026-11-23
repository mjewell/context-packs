import json
from pathlib import Path

from review_wizard_case import SubmitCase, deviation


class NextTests(SubmitCase):
    """next tells the orchestrator what to do now, from what the run folder holds, so it can also pick a run back up."""

    def test_names_each_finder_whose_answer_isnt_in_with_its_prompt(self):
        self.submit_unit(0, 1, [])
        self.submit_unit(2, 1, [])

        run = self.step('next')

        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout,
                         "Waiting on 2 finders, whose answers aren't in yet:\n"
                         f'  unit 1, 2 docs: Run `{self.command("brief", "1")}` and follow what it says.\n'
                         f'  the uncovered finder: Run `{self.command("brief", "3")}` and follow what it says.\n'
                         'If one of them stopped without its answer going in, start it again with the same prompt. '
                         f'When they have all answered, run `{self.command("next")}` again.\n')

    def test_starts_the_merge_once_every_finder_is_in_and_numbers_their_findings(self):
        self.submit_unit(0, 1, [deviation('A')])
        self.submit_unit(1, 2, [deviation('B'), deviation('C')])
        self.submit_unit(2, 1, [])
        self.assertEqual(self.submit(3, [{**deviation('D'), 'kind': 'uncovered choice', 'rules': []}]).returncode, 0)

        run = self.step('next')

        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout, 'All 4 finders are in, with 4 findings.\n'
                                     'Start one subagent with exactly this prompt: Run '
                                     f'`{self.command("brief", "merge")}` and follow what it says.\n'
                                     f'When it has answered, run `{self.command("next")}`.\n')
        sources = json.loads((Path(self.run_dir) / 'sources.json').read_text())
        self.assertEqual([(source['id'], source['finding']['headline']) for source in sources],
                         [('0:0', 'A'), ('1:0', 'B'), ('1:1', 'C'), ('3:0', 'D')])

    def test_keeps_the_finders_answers_once_the_merge_has_started(self):
        for unit, docs in ((0, 1), (1, 2), (2, 1)):
            self.submit_unit(unit, docs, [])
        self.submit(3, [])
        self.step('next')

        run = self.submit(1, [])

        self.assertEqual(run.returncode, 1)
        self.assertIn("Not taken: the merge has started, so the finders' answers can't change.", run.stderr)


class MergeTests(SubmitCase):
    """Once every finder is in, one subagent groups their findings, and the wizard builds the findings from its groups,
    as the merge job's script does."""

    def all_in(self):
        self.submit_unit(0, 1, [deviation('A')])
        self.submit_unit(1, 2, [deviation('B')])
        self.submit_unit(2, 1, [])
        self.assertEqual(self.submit(3, [{**deviation('D'), 'kind': 'uncovered choice', 'rules': []}]).returncode, 0)
        self.assertEqual(self.step('next').returncode, 0)

    def groups(self, groups):
        return self.submit_groups(groups)

    def test_brief_gives_the_merging_agent_the_numbered_findings_and_where_its_groups_go(self):
        self.all_in()

        run = self.step('brief', 'merge')

        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertTrue(run.stdout.startswith("You're merging the finders' answers in a pack review"), run.stdout[:80])
        self.assertIn(f"Every finder's findings, each with an id, are what `{self.command('sources')}` prints.",
                      run.stdout)
        self.assertIn(f"Write your groups as JSON to `{self.answer_path('groups.json')}`, with your tool for writing "
                      'files, not the shell. Then run exactly this command, and do what it prints:\n\n'
                      f"{self.command('submit-groups')}\n\n"
                      'Your groups must fit this JSON Schema:\n\n{\n "type": "object",', run.stdout)
        self.assertIn('Run each command exactly as it is printed here', run.stdout)
        self.assertIn('"ids"', run.stdout)

    def test_sources_prints_the_finders_findings_numbered(self):
        self.all_in()

        run = self.step('sources')

        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual([(source['id'], source['finding']['headline']) for source in json.loads(run.stdout)],
                         [('0:0', 'A'), ('1:0', 'B'), ('3:0', 'D')])

    def test_sources_refuses_before_every_finder_is_in(self):
        run = self.step('sources')

        self.assertEqual(run.returncode, 1)
        self.assertIn(f"The merge can't start yet: run `{self.command('next')}` to see whose answers aren't in.",
                      run.stderr)

    def test_brief_refuses_the_merge_before_every_finder_is_in(self):
        run = self.step('brief', 'merge')

        self.assertEqual(run.returncode, 1)
        self.assertIn(f"The merge can't start yet: run `{self.command('next')}` to see whose answers aren't in.",
                      run.stderr)

    def test_next_waits_on_the_merge_until_its_groups_are_in(self):
        self.all_in()

        run = self.step('next')

        self.assertEqual(run.stdout, "Waiting on the merge, whose groups aren't in yet. If it stopped without its "
                                     'groups going in, start it again with the same prompt: Run '
                                     f'`{self.command("brief", "merge")}` and follow what it says. When it has '
                                     f'answered, run `{self.command("next")}` again.\n')

    def test_refuses_groups_that_leave_out_a_finders_finding(self):
        self.all_in()
        run = self.groups([{'ids': ['0:0', '1:0'], 'kind': 'deviation', 'headline': 'H', 'take': 'T'}])

        self.assertEqual(run.returncode, 1)
        self.assertIn("Not taken: the merge's groups leave out 3:0. Fix your groups, then submit them again with "
                      f"`{self.command('submit-groups')}`.", run.stderr)

    def test_builds_the_findings_from_the_groups_and_next_says_its_done(self):
        self.all_in()
        run = self.groups([{'ids': ['0:0', '1:0'], 'kind': 'deviation', 'headline': 'One import, two rules',
                            'take': 'T'},
                           {'ids': ['3:0'], 'kind': 'uncovered choice', 'headline': 'Where config lives', 'take': 'U'}])

        self.assertEqual(run.returncode, 0, run.stderr)
        path = f'{self.run_dir}/findings.json'
        self.assertEqual(run.stdout, f'2 findings are in {path}. Tell whoever started you, and stop.\n')
        report = json.loads(Path(path).read_text())
        self.assertEqual((report['base'], report['head']), (self.base, self.head))
        self.assertEqual([(found['headline'], len(found['rules']), found['take']) for found in report['findings']],
                         [('One import, two rules', 1, 'T'), ('Where config lives', 0, 'U')])
        done = self.step('next').stdout
        first, rest = done.split('\n', 1)
        self.assertEqual(first, f'Done: 2 findings, 1 deviation and 1 uncovered choice, in {path}. Here they are:')
        self.assertEqual(json.loads(rest), report['findings'])


class GroupTests(SubmitCase):
    """Each finding is built from the finders' findings its group names, so the merge can't drop what they found, and
    groups that would drop, repeat or invent one are refused."""

    NUMBERS = {'file': 'AGENTS.md', 'quote': 'Game numbers live in content.', 'routed': True}
    SIM = {'file': 'docs/testing.md', 'quote': 'Sim code reads its numbers from content.', 'routed': False}

    def found(self, rules=(), spots=(), deliberate=(), exemplars=(), kind='deviation', headline='A finder headline'):
        return {'kind': kind, 'headline': headline, 'rules': list(rules), 'spots': list(spots),
                'deliberate': list(deliberate), 'exemplars': list(exemplars), 'take': 'A finder take.'}

    def spot(self, path, line, follows=False):
        return {'path': path, 'line': line, 'follows': follows}

    def answered(self, unit0=(), unit1=(), unit2=(), uncovered=()):
        """Every finder in, with these findings: unit 0's are 0:0, 0:1 and so on."""
        for unit, docs, findings in ((0, 1, unit0), (1, 2, unit1), (2, 1, unit2)):
            self.submit_unit(unit, docs, list(findings))
        self.assertEqual(self.submit(3, list(uncovered)).returncode, 0)
        self.assertEqual(self.step('next').returncode, 0)

    def group(self, *ids, kind='deviation', headline='A game number in sim code', take='Move it to content.'):
        return {'ids': list(ids), 'kind': kind, 'headline': headline, 'take': take}

    def built(self, groups):
        run = self.submit_groups(groups)
        self.assertEqual(run.returncode, 0, run.stderr)
        return json.loads((Path(self.run_dir) / 'findings.json').read_text())['findings']

    def test_builds_a_finding_from_every_finding_its_group_names(self):
        self.answered(unit0=[self.found(rules=[self.NUMBERS], spots=[self.spot('src/sim.ts', 42)],
                                        deliberate=['Commit abc says so.'])],
                      unit2=[self.found(rules=[self.SIM, self.NUMBERS],
                                        spots=[self.spot('src/sim.ts', 42), self.spot('src/rng.ts', 9)],
                                        deliberate=['Commit abc says so.', 'A comment at the spot.'])])

        [finding] = self.built([self.group('0:0', '2:0')])

        self.assertEqual(finding, {
            'kind': 'deviation', 'headline': 'A game number in sim code', 'take': 'Move it to content.',
            'rules': [self.NUMBERS, self.SIM], 'spots': [self.spot('src/sim.ts', 42), self.spot('src/rng.ts', 9)],
            'deliberate': ['Commit abc says so.', 'A comment at the spot.'], 'exemplars': []})

    def test_counts_a_spot_as_deviating_when_any_finding_says_it_deviates(self):
        self.answered(unit0=[self.found(rules=[self.NUMBERS], spots=[self.spot('src/sim.ts', 42)])],
                      unit1=[self.found(rules=[self.SIM], spots=[self.spot('src/sim.ts', 42, follows=True)])])

        [finding] = self.built([self.group('0:0', '1:0', kind='conflict')])

        self.assertEqual(finding['kind'], 'conflict')
        self.assertEqual(finding['spots'], [self.spot('src/sim.ts', 42)])

    def test_keeps_an_uncovered_choices_exemplars_in_the_finding_that_holds_it(self):
        ways = [{'way': 'Loaded at startup', 'examples': ['src/load.ts:8']}]
        self.answered(unit0=[self.found(rules=[self.NUMBERS], spots=[self.spot('src/load.ts', 3)])],
                      uncovered=[self.found(kind='uncovered choice', spots=[self.spot('src/load.ts', 3)],
                                            exemplars=ways)])

        [finding] = self.built([self.group('0:0', '3:0')])

        self.assertEqual(finding['exemplars'], ways)
        self.assertEqual(finding['rules'], [self.NUMBERS])

    def test_keeps_the_groups_in_the_order_the_agent_gave_them(self):
        self.answered(unit0=[self.found()], unit1=[self.found()])

        findings = self.built([self.group('1:0', headline='Second'), self.group('0:0', headline='First')])

        self.assertEqual([f['headline'] for f in findings], ['Second', 'First'])

    def test_refuses_groups_that_leave_out_repeat_or_invent_a_finders_finding(self):
        self.answered(unit0=[self.found()], unit1=[self.found()])
        for groups, says in (([self.group('0:0')], 'leave out 1:0'),
                             ([self.group('0:0', '1:0'), self.group('1:0')], 'put 1:0 in more than one group'),
                             ([self.group('0:0', '1:0', '9:9')], 'name 9:9, which no finder reported')):
            with self.subTest(says=says):
                run = self.submit_groups(groups)

                self.assertEqual(run.returncode, 1)
                self.assertIn(says, run.stderr)
                self.assertFalse((Path(self.run_dir) / 'findings.json').exists())
