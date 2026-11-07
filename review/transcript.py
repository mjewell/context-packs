#!/usr/bin/env python3
"""Print what the review agent did, from the transcript claude-code-action saves: each tool call with its input, on
one line. A tool's result can hold file contents or anything the agent read, so it shows only whether it was an
error. Secrets are redacted throughout."""
import argparse
import json
from pathlib import Path

from sanitize import SECRETS

WIDTH = 300


def line(indent, text):
    """The text on one line after the indent, redacted, and cut to WIDTH."""
    text = indent + SECRETS.sub('[redacted]', ' '.join(text.split()))
    return text if len(text) <= WIDTH else text[:WIDTH - 1] + '…'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--file', type=Path, required=True, help="claude-code-action's claude-execution-output.json")
    args = parser.parse_args()
    for message in json.loads(args.file.read_text(encoding='utf-8')):
        if message.get('type') not in ('assistant', 'user'):
            continue
        indent = '  [subagent] ' if message.get('parent_tool_use_id') else ''
        for part in message['message']['content']:
            if isinstance(part, str):
                continue
            if part['type'] == 'tool_use':
                print(line(indent, f'{part["name"]} {json.dumps(part["input"], ensure_ascii=False)}'))
            elif part['type'] == 'tool_result' and part.get('is_error'):
                print(f'{indent}  -> error')


if __name__ == '__main__':
    main()
