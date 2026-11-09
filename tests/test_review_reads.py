import json

from review_case import ReviewCase
from test_review_transcript import call, result

DOCS = ['context-packs/project/a.md', 'context-packs/project/b.md']
DOC = 'One.\nTwo.\nThree.\n'


class ReadsTests(ReviewCase):
    """Which of a unit's docs its agent read in full, from the transcript claude-code-action saves: shown in the run's
    log, and written down for the summary when any went unread."""

    def read(self, id, path, parent=None, error=False, **window):
        return [call(id, 'Read', {'file_path': str(self.root / path), **window}, parent=parent),
                result(id, 'the doc', error=error, parent=parent)]

    def report(self, messages, docs=DOCS):
        for path in docs:
            (self.root / path).parent.mkdir(parents=True, exist_ok=True)
            (self.root / path).write_text(DOC)
        (self.root / 'transcript.json').write_text(json.dumps(list(messages)))
        run = self.script('reads', '--transcript', 'transcript.json', '--unread', 'unread.txt',
                          input=json.dumps(docs))
        self.assertEqual(run.returncode, 0, run.stderr)
        return (self.root / 'unread.txt').read_text().splitlines(), run.stdout

    def test_lists_the_docs_the_agent_didnt_read_and_logs_who_read_the_rest(self):
        unread, log = self.report([*self.read('t1', DOCS[0])])

        self.assertEqual(unread, [DOCS[1]])
        self.assertIn(f'read by the agent: {DOCS[0]}', log)
        self.assertIn(f'not read: {DOCS[1]}', log)

    def test_lists_nothing_when_every_doc_was_read(self):
        unread, _ = self.report([*self.read('t1', DOCS[0]), *self.read('t2', DOCS[1])])

        self.assertEqual(unread, [])

    def test_doesnt_count_a_read_of_part_of_a_doc(self):
        unread, _ = self.report(self.read('t1', DOCS[0], limit=2))

        self.assertIn(DOCS[0], unread)

    def test_counts_pages_that_together_cover_a_doc(self):
        unread, _ = self.report([*self.read('t1', DOCS[0], limit=2), *self.read('t2', DOCS[0], offset=3, limit=2)])

        self.assertNotIn(DOCS[0], unread)

    def test_doesnt_count_a_read_that_failed(self):
        unread, _ = self.report(self.read('t1', DOCS[0], error=True))

        self.assertIn(DOCS[0], unread)
