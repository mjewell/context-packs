#!/usr/bin/env python3
"""Stands in for `claude -p` in tests. Reads the instructions file in its working directory, as Claude Code loads it,
and "reads" the doc of each table row whose when appears in the prompt, writing each read as a tool_use line of
stream-json, the way the real command does. Appends its arguments and working directory to $FAKE_CLAUDE_LOG."""
import json
import os
from pathlib import Path
import re
import sys

ROW = re.compile(r'^\| (.+?) \| `(.+?)` \|$', re.MULTILINE)


def main():
    args = sys.argv[1:]
    prompt = args[args.index('-p') + 1]
    cwd = Path.cwd()
    if os.environ.get('FAKE_CLAUDE_LOG'):
        with open(os.environ['FAKE_CLAUDE_LOG'], 'a') as log:
            log.write(json.dumps({'args': args, 'cwd': str(cwd),
                                  'files': sorted(p.relative_to(cwd).as_posix() for p in cwd.rglob('*'))}) + '\n')
    print(json.dumps({'type': 'system', 'subtype': 'init'}))
    instructions = cwd / 'CLAUDE.md'
    text = instructions.read_text() if instructions.exists() else ''
    for when, path in ROW.findall(text):
        if when.lower() in prompt.lower():
            target = Path(path) if Path(path).is_absolute() else cwd / path
            print(json.dumps({'type': 'assistant', 'message': {'content': [
                {'type': 'tool_use', 'id': 'toolu_1', 'name': 'Read', 'input': {'file_path': str(target)}}]}}))
    print(json.dumps({'type': 'result', 'subtype': 'success', 'result': 'Done.'}))


main()
