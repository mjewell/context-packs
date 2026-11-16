"""Which docs, and which changed paths' diffs, the review agent and its subagents read in full, from the transcript
claude-code-action saves. The summary runs it after the agent, so it can't change the answer: it shows whether the
review skipped one. A doc counts as read once one agent was returned every line of it, by one Read or by several pages,
judged by each Read's offset and limit. A diff counts as read once one agent was returned every page of it by the git
server's diff tool."""
import os
from pathlib import Path

from git_server import pages

# How many lines Claude Code's Read returns when it's given no limit.
PAGE = 2000


def succeeded(messages, tool, name):
    """Who made each of the tool's calls that didn't fail, and its input: name for the agent whose transcript it is, or
    a subagent numbered in the order it started."""
    calls, failed, agents = {}, set(), {}
    for message in messages:
        if message.get('type') not in ('assistant', 'user'):
            continue
        parent = message.get('parent_tool_use_id')
        reader = name if parent is None else agents.setdefault(parent, f'subagent {len(agents) + 1}')
        for part in message['message']['content']:
            if isinstance(part, str):
                continue
            if part['type'] == 'tool_use' and part['name'] == tool:
                calls[part['id']] = (reader, part['input'])
            elif part['type'] == 'tool_result' and part.get('is_error'):
                failed.add(part['tool_use_id'])
    return [call for id, call in calls.items() if id not in failed]


def covered(messages, checkout, name):
    """The lines of each file in the checkout, by its path from there, that each agent's successful Reads returned,
    keyed by who read them."""
    lines = {}
    for reader, input in succeeded(messages, 'Read', name):
        path = os.path.relpath(os.path.realpath(input['file_path']), checkout)
        if path.startswith('..'):
            continue
        start = max(input.get('offset') or 1, 1)
        lines.setdefault(Path(path).as_posix(), {}).setdefault(reader, set()).update(
            range(start, start + (input.get('limit') or PAGE)))
    return lines


def readers(messages, docs, checkout, name):
    """Who read each doc in the checkout, by its path from there, in full: none for a doc no agent read."""
    lines = covered(messages, checkout, name)
    found = {}
    for doc in docs:
        whole = set(range(1, len((Path(checkout) / doc).read_text(encoding='utf-8').splitlines()) + 1))
        found[doc] = [reader for reader, seen in lines.get(doc, {}).items() if whole <= seen]
    return found


def diff_readers(messages, changed, name):
    """Who read each changed path's diff in full, from the (lines, path) pairs the git server's changed tool lists:
    none for a path no agent read."""
    seen = {}
    for reader, input in succeeded(messages, 'mcp__git__diff', name):
        seen.setdefault(input['path'], {}).setdefault(reader, set()).add(input.get('page', 1))
    return {path: [reader for reader, got in seen.get(path, {}).items() if set(range(1, pages(lines) + 1)) <= got]
            for lines, path in changed}
