import json
import shlex
import subprocess
import sys
import unittest

from review_case import REVIEW

INPUTS = '/runner/temp/pack-review.abc123'


FINDING = json.loads((REVIEW / 'findings.schema.json').read_text())['properties']['findings']['items']


class ArgsTests(unittest.TestCase):
    """The arguments the review workflow hands claude-code-action for each agent: one per unit of docs, and the one
    that merges their answers."""

    def args(self, *extra, answer='unit'):
        run = subprocess.run([sys.executable, str(REVIEW / 'args.py'), '--answer', answer, '--inputs', INPUTS, *extra],
                             capture_output=True, text=True, check=True)
        self.assertEqual(run.stdout.count('\n'), 1)
        return shlex.split(run.stdout)

    def flag(self, args, name):
        return args[args.index(name) + 1]

    def schema(self, answer):
        return json.loads(self.flag(self.args(answer=answer), '--json-schema'))

    def test_loads_the_skill_for_either_answer(self):
        for answer in ('unit', 'merge'):
            self.assertEqual(self.flag(self.args(answer=answer), '--plugin-dir'), str(REVIEW.parent))

    def test_a_unit_answers_with_its_deviations_as_findings_and_the_rules_it_found_followed(self):
        schema = self.schema('unit')

        self.assertEqual(sorted(schema['required']), ['deviations', 'followed'])
        deviation = schema['properties']['deviations']['items']
        self.assertEqual(deviation['properties']['kind'], {'enum': ['deviates']})
        self.assertEqual({**deviation['properties'], 'kind': FINDING['properties']['kind']}, FINDING['properties'])
        followed = schema['properties']['followed']['items']
        self.assertEqual(followed['properties']['rule'], FINDING['properties']['rules']['items'])
        self.assertEqual(followed['properties']['spots'], FINDING['properties']['spots'])

    def test_the_merge_answers_with_only_conflicts_and_uncovered_choices(self):
        schema = self.schema('merge')

        finding = schema['properties']['findings']['items']
        self.assertEqual(finding['properties']['kind'], {'enum': ['conflicting', 'uncovered']})
        self.assertEqual({**finding['properties'], 'kind': FINDING['properties']['kind']}, FINDING['properties'])

    def test_gives_the_agent_no_mcp_servers(self):
        args = self.args()

        self.assertNotIn('--mcp-config', args)
        self.assertIn('--strict-mcp-config', args)

    def test_gives_the_agent_tools_that_only_read_the_checkout_and_the_diff(self):
        args = self.args()

        self.assertEqual(self.flag(args, '--tools'), 'Read,Glob,Grep')
        self.assertEqual(self.flag(args, '--allowedTools'), 'Read,Glob,Grep')
        self.assertEqual(self.flag(args, '--add-dir'), INPUTS)
        self.assertEqual(self.flag(args, '--disallowedTools'), 'Read(./.git/**)')
        self.assertIn('--restricted', args)

    def test_passes_a_model_when_given_one(self):
        self.assertEqual(self.flag(self.args('--model', 'opus'), '--model'), 'opus')
        self.assertNotIn('--model', self.args('--model', ''))

    def test_quotes_each_value_whole_so_any_shell_style_parser_reads_it_the_same(self):
        line = subprocess.run([sys.executable, str(REVIEW / 'args.py'), '--answer', 'unit', '--inputs', INPUTS],
                              capture_output=True, text=True, check=True).stdout
        for value in shlex.split(line):
            quoted = shlex.quote(value)
            self.assertTrue(quoted == value or (quoted.startswith("'") and quoted.count("'") == 2), value[:60])
