from pathlib import Path

from review_wizard_case import SubmitCase, deviation


class SubmitTests(SubmitCase):
    """submit takes a finder's answer only when it's whole: in the schema's shape, and after every doc of its unit was
    read through doc. A refusal says what to do, then to submit again."""

    def test_takes_an_answer_once_every_doc_was_read(self):
        self.read_docs(1, 2)

        run = self.submit(1, [deviation()])

        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout, 'Unit 1 is in, with 1 finding. Tell whoever started you that unit 1 is in, and '
                                     'stop.\n')

    def test_refuses_an_answer_before_every_doc_was_read_and_names_the_commands_left(self):
        self.read_docs(1, 1)

        run = self.submit(1, [deviation()])

        self.assertEqual(run.returncode, 1)
        self.assertEqual(run.stdout, '')
        self.assertIn(f"Not taken: you didn't read docs/git.md through `{self.command('doc', '1', '2')}`. Read it, "
                      'check the diff against it, update your answer, then submit it again with '
                      f"`{self.command('submit', '1')}`.", run.stderr)
        self.assertFalse((Path(self.run_dir) / 'accepted' / 'unit-1.json').exists())

    def test_takes_the_uncovered_finders_answer_without_any_doc_read(self):
        run = self.submit(3, [])

        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout, "The uncovered finder's answer is in, with 0 findings. Tell whoever started you "
                                     "that the uncovered finder's answer is in, and stop.\n")

    def test_refuses_an_answer_that_breaks_the_schema_and_names_where(self):
        broken = deviation()
        broken['spots'][0]['line'] = '12'
        del broken['take']
        broken['kind'] = 'nit'
        self.read_docs(1, 2)

        run = self.submit(1, [broken])

        self.assertEqual(run.returncode, 1)
        self.assertIn('Not taken: your answer breaks the schema:\n'
                      '  findings[0] needs take\n'
                      '  findings[0].kind must be one of "deviation", "conflict", "uncovered choice"\n'
                      '  findings[0].spots[0].line must be an integer\n'
                      f"Fix it, then submit it again with `{self.command('submit', '1')}`.", run.stderr)

    def test_refuses_an_answer_with_a_key_the_schema_doesnt_have(self):
        extra = {**deviation(), 'severity': 'high'}
        self.read_docs(1, 2)

        run = self.submit(1, [extra])

        self.assertEqual(run.returncode, 1)
        self.assertIn('  findings[0] has severity, which the schema has no place for\n', run.stderr)

    def test_refuses_an_answer_that_isnt_json(self):
        self.read_docs(1, 2)

        run = self.submit(1, '{"findings": [')

        self.assertEqual(run.returncode, 1)
        self.assertIn("Not taken: your answer isn't JSON", run.stderr)

    def test_refuses_a_submit_with_nothing_on_stdin_and_shows_how_to_send_it(self):
        self.read_docs(1, 2)

        run = self.step('submit', '1')

        self.assertEqual(run.returncode, 1)
        self.assertIn('Not taken: no answer came on stdin. Write it as JSON to a file in your scratchpad, then run '
                      f"`{self.command('submit', '1')} < <file>` with that file's path.", run.stderr)
