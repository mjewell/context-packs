import json

from review_case import ReviewCase

DOCS = ['context-packs/gen/core/testing.md', 'context-packs/gen/core/git-and-prs.md',
        'context-packs/project/review.md']
# How many lines each doc in the checkout has.
LINES = 30


class Transcript:
    """A session's transcript as Claude Code writes it: one JSON object per line, in the shape a real run wrote."""

    def __init__(self, path, checkout, sidechain):
        self.path, self.checkout, self.sidechain, self.calls = path, checkout, sidechain, 0
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text('')

    def add(self, role, content):
        line = {'type': role, 'isSidechain': self.sidechain, 'message': {'role': role, 'content': content}}
        with self.path.open('a') as file:
            file.write(json.dumps(line) + '\n')

    def prompt(self, text):
        self.add('user', text)

    def stop_feedback(self, reason):
        """What Claude Code adds to a subagent's transcript when a SubagentStop hook sends it back."""
        self.add('user', f'Stop hook feedback:\n{reason}')

    def call(self, name, input, result, error=False):
        self.calls += 1
        id = f'toolu_{self.calls}'
        self.add('assistant', [{'type': 'tool_use', 'id': id, 'name': name, 'input': input, 'caller': {'type': 'direct'}}])
        self.add('user', [{'type': 'tool_result', 'tool_use_id': id, 'content': result,
                           **({'is_error': True} if error else {})}])

    def read(self, doc, error=False, **page):
        """A Read of the doc, with the offset and limit given in page, if any."""
        self.call('Read', {'file_path': str(self.checkout / doc), **page},
                  'File does not exist.' if error else '1\tA rule.\n', error)


class ReadGateTests(ReviewCase):
    """The hooks that keep the review agent and each of its subagents from finishing before reading their docs."""

    def setUp(self):
        super().setUp()
        self.checkout = self.root / 'checkout'
        self.inputs = self.root / 'inputs'
        self.inputs.mkdir()
        (self.inputs / 'docs.txt').write_text(''.join(f'{doc}\n' for doc in DOCS))
        for doc in DOCS:
            (self.checkout / doc).parent.mkdir(parents=True, exist_ok=True)
            (self.checkout / doc).write_text(''.join(f'Rule {n}.\n' for n in range(1, LINES + 1)))
        self.sessions = self.root / 'projects' / 'session'
        self.main = Transcript(self.root / 'projects' / 'session.jsonl', self.checkout, sidechain=False)
        self.subagents = 0

    def subagent(self, docs):
        """A subagent the main agent gave docs to check, by their paths in its prompt."""
        self.subagents += 1
        transcript = Transcript(self.sessions / 'subagents' / f'agent-{self.subagents}.jsonl', self.checkout,
                                sidechain=True)
        transcript.prompt('Check these docs against the diff at /inputs/diff.patch, reading each in full:\n'
                          + ''.join(f'- {self.checkout / doc}\n' for doc in docs))
        return transcript

    def hook(self, gate, input):
        run = self.script('reads', gate, '--inputs', self.inputs, input=json.dumps(input))
        self.assertEqual(run.returncode, 0, run.stderr)
        return json.loads(run.stdout) if run.stdout.strip() else None

    def stop(self, transcript):
        """What the gate answers when the subagent tries to finish."""
        return self.hook('subagent', {
            'hook_event_name': 'SubagentStop', 'cwd': str(self.checkout), 'transcript_path': str(self.main.path),
            'agent_id': transcript.path.stem, 'agent_transcript_path': str(transcript.path),
            'stop_hook_active': False})

    def test_sends_a_subagent_back_for_the_docs_it_was_given_and_hasnt_read(self):
        subagent = self.subagent(DOCS[:2])
        subagent.read(DOCS[0])

        answer = self.stop(subagent)

        self.assertEqual(answer['decision'], 'block')
        self.assertIn(DOCS[1], answer['reason'])
        self.assertNotIn(DOCS[0], answer['reason'])
        self.assertNotIn(DOCS[2], answer['reason'])

    def test_counts_only_reads_that_returned_the_doc(self):
        subagent = self.subagent(DOCS[:1])
        subagent.read(DOCS[0], error=True)

        self.assertIn(DOCS[0], self.stop(subagent)['reason'])

    def test_lets_a_subagent_finish_once_it_has_read_its_docs(self):
        subagent = self.subagent(DOCS[:2])
        subagent.read(DOCS[1])
        subagent.read(DOCS[0])

        self.assertIsNone(self.stop(subagent))

    def test_gives_up_on_a_subagent_after_sending_it_back_three_times(self):
        subagent = self.subagent(DOCS[:1])
        for _ in range(3):
            subagent.stop_feedback(self.stop(subagent)['reason'])

        self.assertIsNone(self.stop(subagent))

    def test_doesnt_count_the_gates_words_in_a_subagents_prompt_as_sending_it_back(self):
        reason = self.stop(self.subagent(DOCS[:1]))['reason']
        relayed = Transcript(self.sessions / 'subagents' / 'agent-relayed.jsonl', self.checkout, sidechain=True)
        relayed.prompt(f'The review was told: {reason}\nRead {self.checkout / DOCS[0]} and check it.')
        for _ in range(2):
            relayed.stop_feedback(self.stop(relayed)['reason'])

        self.assertEqual(self.stop(relayed)['decision'], 'block')

    def answer(self):
        """What the gate answers when the main agent calls StructuredOutput with its findings."""
        return self.hook('answer', {
            'hook_event_name': 'PreToolUse', 'cwd': str(self.checkout), 'transcript_path': str(self.main.path),
            'tool_name': 'StructuredOutput', 'tool_input': {'findings': []}, 'tool_use_id': 'toolu_answer'})

    def denied(self, decision):
        """The reason the gate denied the answer for."""
        output = decision['hookSpecificOutput']
        self.assertEqual((output['hookEventName'], output['permissionDecision']), ('PreToolUse', 'deny'))
        return output['permissionDecisionReason']

    def test_denies_the_answer_while_a_doc_is_unread(self):
        self.main.read(DOCS[0])
        self.main.read(DOCS[2])

        reason = self.denied(self.answer())

        self.assertIn(DOCS[1], reason)
        self.assertNotIn(DOCS[0], reason)

    def test_counts_the_docs_a_finished_subagent_read(self):
        self.main.read(DOCS[0])
        subagent = self.subagent(DOCS[1:])
        subagent.read(DOCS[1])
        subagent.read(DOCS[2])
        self.stop(subagent)

        self.assertIsNone(self.answer())

    def test_doesnt_count_a_subagent_that_hasnt_finished(self):
        self.main.read(DOCS[0])
        self.main.read(DOCS[1])
        running = self.subagent(DOCS[2:])
        running.read(DOCS[2])

        self.assertIn(DOCS[2], self.denied(self.answer()))

    def test_lets_the_answer_through_after_three_denials_and_lists_what_went_unread(self):
        self.main.read(DOCS[0])
        for _ in range(3):
            reason = self.denied(self.answer())
            self.main.call('StructuredOutput', {'findings': []}, f'PreToolUse:StructuredOutput hook error: {reason}',
                           error=True)

        self.assertIsNone(self.answer())
        self.assertEqual((self.inputs / 'unread.txt').read_text(), f'{DOCS[1]}\n{DOCS[2]}\n')

    def test_lists_nothing_when_every_doc_was_read(self):
        for doc in DOCS:
            self.main.read(doc)

        self.assertIsNone(self.answer())
        self.assertFalse((self.inputs / 'unread.txt').exists())

    def test_lists_what_went_unread_when_the_agent_stops_after_a_denial(self):
        self.main.read(DOCS[0])

        self.denied(self.answer())

        self.assertEqual((self.inputs / 'unread.txt').read_text(), f'{DOCS[1]}\n{DOCS[2]}\n')

    def test_clears_the_list_once_the_docs_are_read(self):
        self.denied(self.answer())
        for doc in DOCS:
            self.main.read(doc)

        self.assertIsNone(self.answer())
        self.assertFalse((self.inputs / 'unread.txt').exists())

    def test_doesnt_count_a_read_of_part_of_a_doc(self):
        subagent = self.subagent(DOCS[:1])
        subagent.read(DOCS[0], limit=12)

        self.assertIn(DOCS[0], self.stop(subagent)['reason'])

    def test_counts_pages_that_together_cover_a_doc(self):
        subagent = self.subagent(DOCS[:1])
        subagent.read(DOCS[0], limit=12)
        subagent.read(DOCS[0], offset=13, limit=LINES)

        self.assertIsNone(self.stop(subagent))

    def test_doesnt_count_pages_that_leave_a_gap(self):
        subagent = self.subagent(DOCS[:1])
        subagent.read(DOCS[0], limit=12)
        subagent.read(DOCS[0], offset=14, limit=LINES)

        self.assertIn(DOCS[0], self.stop(subagent)['reason'])
