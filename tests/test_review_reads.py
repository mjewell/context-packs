from test_review_summary import SummaryCase, block, reads
from test_review_transcript import call, result

PACKS = [['context-packs/project/a.md', 'context-packs/project/b.md'], ['context-packs/gen/core/c.md']]


class ReadsTests(SummaryCase):
    """Which docs the finders and the merging agent read in full, from each one's transcript: shown in the run's log,
    and listed in the summary when any went unread. The units are the instruction file, then each pack."""

    def read(self, id, path, error=False, **window):
        return [call(id, 'Read', {'file_path': str(self.root / path), **window}),
                result(id, 'the doc', error=error)]

    def unread(self, finders, messages=()):
        run = self.summarize([], docs=PACKS, finders=finders, messages=messages)
        self.assertEqual(run.returncode, 0, run.stderr)
        return block(self.body())[0]['unread'], run.stdout

    def everything(self):
        return [reads(self.root, ['AGENTS.md']), reads(self.root, PACKS[0]), reads(self.root, PACKS[1])]

    def test_lists_the_docs_no_agent_read_and_logs_who_read_the_rest(self):
        unread, log = self.unread([reads(self.root, ['AGENTS.md']), self.read('t1', 'context-packs/project/a.md'), []],
                                  messages=self.read('m1', 'context-packs/project/b.md'))

        self.assertEqual(unread, ['context-packs/gen/core/c.md'])
        self.assertIn("read by unit 0's finder: AGENTS.md", log)
        self.assertIn("read by unit 1's finder: context-packs/project/a.md", log)
        self.assertIn('read by the merging agent: context-packs/project/b.md', log)
        self.assertIn('not read: context-packs/gen/core/c.md', log)

    def test_lists_nothing_when_every_doc_was_read(self):
        unread, _ = self.unread(self.everything())

        self.assertEqual(unread, [])

    def test_lists_the_instruction_file_when_its_finder_skipped_it(self):
        finders = self.everything()
        finders[0] = []

        unread, _ = self.unread(finders)

        self.assertEqual(unread, ['AGENTS.md'])

    def test_doesnt_count_a_read_of_part_of_a_doc(self):
        finders = self.everything()
        finders[1] = [*self.read('t1', 'context-packs/project/a.md', limit=2),
                      *self.read('t2', 'context-packs/project/b.md')]

        unread, _ = self.unread(finders)

        self.assertEqual(unread, ['context-packs/project/a.md'])

    def test_counts_pages_that_together_cover_a_doc(self):
        finders = self.everything()
        finders[1] = [*self.read('t1', 'context-packs/project/a.md', limit=2),
                      *self.read('t2', 'context-packs/project/a.md', offset=3, limit=2),
                      *self.read('t3', 'context-packs/project/b.md')]

        unread, _ = self.unread(finders)

        self.assertEqual(unread, [])

    def test_doesnt_count_a_read_that_failed(self):
        finders = self.everything()
        finders[2] = self.read('t1', 'context-packs/gen/core/c.md', error=True)

        unread, _ = self.unread(finders)

        self.assertEqual(unread, ['context-packs/gen/core/c.md'])

    def test_stops_when_a_finders_record_is_missing(self):
        self.summarize([], docs=PACKS)
        (self.root / 'units' / 'unit-2.json').unlink()

        run = self.report()

        self.assertEqual(run.returncode, 1)
        self.assertIn('unit 2', run.stderr)
