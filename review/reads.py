#!/usr/bin/env python3
"""Which of a unit's docs its agent read in full, from the transcript claude-code-action saves. Each unit job runs it
after its agent, so it can't change the answer: it shows whether the review skipped a doc, in the log and in the
summary. A doc counts
as read once one agent was returned every line of it, by one Read or by several pages, judged by each Read's offset
and limit."""
import argparse
import json
import os
from pathlib import Path
import sys

# How many lines Claude Code's Read returns when it's given no limit.
PAGE = 2000


def covered(messages, checkout):
    """The lines of each file in the checkout, by its path from there, that each agent's successful Reads returned,
    keyed by who read them: the agent, or a subagent numbered in the order it started."""
    calls, failed, agents = {}, set(), {}
    for message in messages:
        if message.get('type') not in ('assistant', 'user'):
            continue
        parent = message.get('parent_tool_use_id')
        reader = 'the agent' if parent is None else agents.setdefault(parent, f'subagent {len(agents) + 1}')
        for part in message['message']['content']:
            if isinstance(part, str):
                continue
            if part['type'] == 'tool_use' and part['name'] == 'Read':
                calls[part['id']] = (reader, part['input'])
            elif part['type'] == 'tool_result' and part.get('is_error'):
                failed.add(part['tool_use_id'])
    lines = {}
    for id, (reader, input) in calls.items():
        path = os.path.relpath(os.path.realpath(input['file_path']), checkout)
        if id in failed or path.startswith('..'):
            continue
        start = max(input.get('offset') or 1, 1)
        lines.setdefault(Path(path).as_posix(), {}).setdefault(reader, set()).update(
            range(start, start + (input.get('limit') or PAGE)))
    return lines


def readers(messages, docs, checkout):
    """Who read each doc in the checkout, by its path from there, in full: none for a doc no agent read."""
    lines = covered(messages, checkout)
    found = {}
    for doc in docs:
        whole = set(range(1, len((Path(checkout) / doc).read_text(encoding='utf-8').splitlines()) + 1))
        found[doc] = [reader for reader, seen in lines.get(doc, {}).items() if whole <= seen]
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--transcript', type=Path, required=True, help="claude-code-action's claude-execution-output.json")
    parser.add_argument('--unread', type=Path, required=True, help="where to list the docs the agent didn't read in full")
    args = parser.parse_args()
    docs = json.loads(sys.stdin.read())
    found = readers(json.loads(args.transcript.read_text(encoding='utf-8')), docs, os.path.realpath('.'))
    for doc, who in found.items():
        print(f'read by {", ".join(who)}: {doc}' if who else f'not read: {doc}')
    args.unread.write_text(''.join(f'{doc}\n' for doc, who in found.items() if not who), encoding='utf-8')


if __name__ == '__main__':
    main()
