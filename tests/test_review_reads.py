from test_review_summary import SummaryCase, block
from test_review_transcript import call, result

PACKS = [['context-packs/project/a.md', 'context-packs/project/b.md'], ['context-packs/gen/core/c.md']]


class ReadsTests(SummaryCase):
    """Which docs the review agent and its subagents read in full, from the transcript claude-code-action saves: shown
    in the run's log, and listed in the summary when any went unread."""

    def read(self, id, path, parent=None, error=False, **window):
        return [call(id, 'Read', {'file_path': str(self.root / path), **window}, parent=parent),
                result(id, 'the doc', error=error, parent=parent)]

    def unread(self, messages):
        run = self.summarize([], docs=PACKS, messages=messages)
        self.assertEqual(run.returncode, 0, run.stderr)
        return block(self.body())[0]['unread'], run.stdout

    def test_lists_the_docs_no_agent_read_and_logs_who_read_the_rest(self):
        unread, log = self.unread([
            *self.read('t1', 'context-packs/project/a.md'),
            call('t2', 'Agent', {'description': 'Check the project pack'}),
            *self.read('s1', 'context-packs/project/b.md', parent='t2'),
            result('t2', 'ledger'),
        ])

        self.assertEqual(unread, ['context-packs/gen/core/c.md'])
        self.assertIn('read by the agent: context-packs/project/a.md', log)
        self.assertIn('read by subagent 1: context-packs/project/b.md', log)
        self.assertIn('not read: context-packs/gen/core/c.md', log)

    def test_lists_nothing_when_every_doc_was_read(self):
        unread, _ = self.unread([*self.read('t1', 'context-packs/project/a.md'),
                                 *self.read('t2', 'context-packs/project/b.md'),
                                 *self.read('t3', 'context-packs/gen/core/c.md')])

        self.assertEqual(unread, [])

    def test_doesnt_count_a_read_of_part_of_a_doc(self):
        unread, _ = self.unread(self.read('t1', 'context-packs/project/a.md', limit=2))

        self.assertIn('context-packs/project/a.md', unread)

    def test_counts_pages_that_together_cover_a_doc(self):
        unread, _ = self.unread([*self.read('t1', 'context-packs/project/a.md', limit=2),
                                 *self.read('t2', 'context-packs/project/a.md', offset=3, limit=2)])

        self.assertNotIn('context-packs/project/a.md', unread)

    def test_doesnt_count_a_read_that_failed(self):
        unread, _ = self.unread(self.read('t1', 'context-packs/project/a.md', error=True))

        self.assertIn('context-packs/project/a.md', unread)
