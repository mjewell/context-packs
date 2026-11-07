import json

from review_case import ReviewCase


def call(id, name, input, parent=None):
    return {'type': 'assistant', 'parent_tool_use_id': parent,
            'message': {'content': [{'type': 'text', 'text': 'Thinking out loud.'},
                                    {'type': 'tool_use', 'id': id, 'name': name, 'input': input}]}}


def result(id, text, error=False, parent=None):
    return {'type': 'user', 'parent_tool_use_id': parent,
            'message': {'content': [{'type': 'tool_result', 'tool_use_id': id, 'is_error': error,
                                     'content': [{'type': 'text', 'text': text}]}]}}


class TranscriptTests(ReviewCase):
    """What a review run's log shows of what the agent did: each tool call, but never what a tool returned."""

    def show(self, messages):
        (self.root / 'transcript.json').write_text(json.dumps(messages))
        run = self.script('transcript', '--file', 'transcript.json')
        self.assertEqual(run.returncode, 0, run.stderr)
        return run.stdout

    def test_lists_each_tool_call_with_its_input(self):
        out = self.show([
            {'type': 'system', 'subtype': 'init'},
            call('t1', 'Read', {'file_path': '/w/AGENTS.md'}),
            result('t1', 'the whole of AGENTS.md'),
            call('t2', 'Bash', {'command': 'git diff b...h'}),
            result('t2', 'diff --git ...'),
            {'type': 'result', 'subtype': 'success', 'num_turns': 3},
        ])

        self.assertEqual(out, 'Read {"file_path": "/w/AGENTS.md"}\nBash {"command": "git diff b...h"}\n')

    def test_marks_the_calls_a_subagent_made(self):
        out = self.show([
            call('t1', 'Agent', {'description': 'Check the core pack'}),
            call('s1', 'Read', {'file_path': '/w/context-packs/gen/core/testing.md'}, parent='t1'),
            result('s1', 'testing doc', parent='t1'),
            result('t1', 'ledger'),
        ])

        self.assertEqual(out, 'Agent {"description": "Check the core pack"}\n'
                              '  [subagent] Read {"file_path": "/w/context-packs/gen/core/testing.md"}\n')

    def test_marks_another_tools_error_without_showing_what_it_returned(self):
        out = self.show([call('t1', 'Read', {'file_path': '/etc/passwd'}),
                         result('t1', 'root:x:0:0 and a secret', error=True)])

        self.assertEqual(out, 'Read {"file_path": "/etc/passwd"}\n  -> error\n')
        self.assertNotIn('secret', out)

    def test_shortens_a_long_input_and_keeps_it_on_one_line(self):
        out = self.show([call('t1', 'Agent', {'prompt': 'Read every doc.\n' + 'x' * 500})])

        [line] = out.splitlines()
        self.assertLessEqual(len(line), 300)
        self.assertTrue(line.endswith('…'))

    def test_redacts_secrets_in_inputs(self):
        token = 'ghs_' + 'a' * 36
        out = self.show([call('t1', 'Grep', {'pattern': f'Key {token}'})])

        self.assertNotIn(token, out)
        self.assertIn('[redacted]', out)
