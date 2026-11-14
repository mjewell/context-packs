from test_review_summary import SummaryCase, block
from test_review_transcript import call, result

# Three paths, as the git server's changed tool lists them: long.txt's diff takes three pages.
CHANGED = [(9, 'a.txt'), (2506, 'long.txt'), (7, 'package-lock.json')]


class UnreadDiffsTests(SummaryCase):
    """Which changed paths' diffs no agent read every page of, from the transcript: shown in the run's log, and
    listed in the summary's JSON. Skipping a lock file is often right, so they don't make the review partial."""

    def diff(self, id, path, parent=None, error=False, **page):
        return [call(id, 'mcp__git__diff', {'path': path, **page}, parent=parent),
                result(id, 'the diff', error=error, parent=parent)]

    def unread(self, messages, findings=()):
        run = self.summarize(findings, messages=messages, changed=CHANGED)
        self.assertEqual(run.returncode, 0, run.stderr)
        return block(self.body())[0]['unread_diffs'], run.stdout

    def test_lists_the_paths_no_agent_read_and_logs_who_read_the_rest(self):
        unread, log = self.unread([
            *self.diff('t1', 'a.txt'),
            call('t2', 'Agent', {'description': 'Check the project pack'}),
            *[part for page in (1, 2, 3) for part in self.diff(f's{page}', 'long.txt', parent='t2', page=page)],
            result('t2', 'ledger'),
        ])

        self.assertEqual(unread, ['package-lock.json'])
        self.assertIn('diff read by the agent: a.txt', log)
        self.assertIn('diff read by subagent 1: long.txt', log)
        self.assertIn('diff not read: package-lock.json', log)

    def test_doesnt_count_a_diff_one_agent_read_only_part_of(self):
        unread, _ = self.unread([
            *self.diff('t1', 'long.txt'),
            call('t2', 'Agent', {'description': 'Check the project pack'}),
            *self.diff('s1', 'long.txt', parent='t2', page=2),
            *self.diff('s2', 'long.txt', parent='t2', page=3),
            result('t2', 'ledger'),
        ])

        self.assertIn('long.txt', unread)

    def test_doesnt_count_a_call_that_failed(self):
        unread, _ = self.unread([*self.diff('t1', 'a.txt', error=True)])

        self.assertIn('a.txt', unread)

    def test_doesnt_make_the_review_partial(self):
        self.unread([])

        body = self.body()
        self.assertIn('found nothing.', body)
        self.assertNotIn('skipped', body)
        self.assertNotIn('/pack-review', body)

    def test_cleans_the_paths_like_the_findings(self):
        run = self.summarize([], changed=[(7, 'a\u200b.txt')])

        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(block(self.body())[0]['unread_diffs'], ['a.txt'])
