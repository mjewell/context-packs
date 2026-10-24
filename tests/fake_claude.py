#!/usr/bin/env python3
"""Stands in for `claude -p` in tests. Reads the instructions file in its working directory, as Claude Code loads it,
and "reads" the doc of each table row whose when appears in the prompt, following rows in what it reads, writing
each read as a tool_use line of stream-json, the way the real command does. With $FAKE_CLAUDE_SLEEP, it then goes
on working that many seconds, as a real session does after its reads. Appends its arguments and working directory to
$FAKE_CLAUDE_LOG."""
import json
import os
from pathlib import Path
import re
import sys
import time

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
    seen = set()

    def follow(text):
        """Read the doc of each row whose when the prompt contains, and the rows of each one read, as an agent follows
        a row to a pack's index."""
        for when, path in ROW.findall(text):
            target = Path(path) if Path(path).is_absolute() else cwd / path
            if when.lower() in prompt.lower() and target not in seen:
                seen.add(target)
                print(json.dumps({'type': 'assistant', 'message': {'content': [
                    {'type': 'tool_use', 'id': 'toolu_1', 'name': 'Read', 'input': {'file_path': str(target)}}]}}),
                      flush=True)
                if target.is_file():
                    follow(target.read_text())

    follow(instructions.read_text() if instructions.exists() else '')
    time.sleep(float(os.environ.get('FAKE_CLAUDE_SLEEP', '0')))
    print(json.dumps({'type': 'result', 'subtype': 'success', 'result': 'Done.'}))


main()
