#!/usr/bin/env python3
"""Print, on one line, the claude_args the review action hands claude-code-action: the pack-review skill, the
review's MCP tools for the PR, the schema the agent's answer is checked against, and tools that only read the
checkout and the folder holding the diff and log. claude-code-action splits the line the way a shell would."""
import argparse
import json
from pathlib import Path
import shlex
import sys

REVIEW = Path(__file__).resolve().parent
SERVER = 'pack-review'
TOOLS = ['read_comments', 'open_thread', 'reply']
# The agent reads the PR, which is untrusted text, so its own tools only read: confined by --restricted to the
# checkout, without .git/config, where claude-code-action keeps its token, and to the folder the action wrote the
# diff and log to. It gets no shell, since an allowed git command such as git log --output=<file> writes any file.
# It writes to the PR only through the review's tools.
BUILT_IN = ['Read', 'Glob', 'Grep', 'Agent']
ALLOWED = [*BUILT_IN, *[f'mcp__{SERVER}__{tool}' for tool in TOOLS]]


def compact(value):
    """JSON on one line, with each ' written as \\u0027 so the whole value fits in one pair of single quotes."""
    return json.dumps(value, separators=(',', ':')).replace("'", '\\u0027')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pr', required=True, help='the PR number')
    parser.add_argument('--head', required=True, help='the commit under review')
    parser.add_argument('--inputs', required=True, help='the folder holding the diff and log the agent reviews')
    parser.add_argument('--model', default='', help="the model to review with, if not Claude Code's default")
    args = parser.parse_args()
    server = {'command': 'python3', 'args': [str(REVIEW / 'tools.py'), '--pr', args.pr, '--head', args.head]}
    schema = json.loads((REVIEW / 'findings.schema.json').read_text(encoding='utf-8'))
    values = ['--plugin-dir', str(REVIEW.parent), '--mcp-config', compact({'mcpServers': {SERVER: server}}),
              '--json-schema', compact(schema), '--tools', ','.join(BUILT_IN), '--allowedTools', ','.join(ALLOWED),
              '--add-dir', args.inputs, '--disallowedTools', 'Read(./.git/**)', *(['--model', args.model] if args.model else []),
              '--restricted', '--strict-mcp-config']
    quoted = [value for value in values if "'" in value]
    if quoted:
        sys.exit(f'pack-review: these arguments hold a single quote, which claude-code-action may split: {quoted}')
    print(' '.join(shlex.quote(value) for value in values))


if __name__ == '__main__':
    main()
