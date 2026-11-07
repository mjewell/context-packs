#!/usr/bin/env python3
"""Print, on one line, the claude_args the review action hands claude-code-action: the pack-review skill, the schema
the agent's answer is checked against, and tools that only read the checkout and the folder holding the diff and log.
claude-code-action splits the line the way a shell would."""
import argparse
import json
from pathlib import Path
import shlex
import sys

REVIEW = Path(__file__).resolve().parent
# The diff and the repo's files can hold text written to steer the agent, so its tools only read:
# confined by --restricted to the checkout, without .git/config, where claude-code-action keeps its token, and to
# the folder the action wrote the diff and log to. It gets no shell, since an allowed git command such as
# git log --output=<file> writes any file, and no MCP servers, so nothing it does reaches the PR.
TOOLS = ['Read', 'Glob', 'Grep', 'Agent']


def compact(value):
    """JSON on one line, with each ' written as \\u0027 so the whole value fits in one pair of single quotes."""
    return json.dumps(value, separators=(',', ':')).replace("'", '\\u0027')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', required=True, help='the folder holding the diff and log the agent reviews')
    parser.add_argument('--model', default='', help="the model to review with, if not Claude Code's default")
    args = parser.parse_args()
    schema = json.loads((REVIEW / 'findings.schema.json').read_text(encoding='utf-8'))
    values = ['--plugin-dir', str(REVIEW.parent), '--json-schema', compact(schema), '--tools', ','.join(TOOLS),
              '--allowedTools', ','.join(TOOLS), '--add-dir', args.inputs, '--disallowedTools', 'Read(./.git/**)',
              *(['--model', args.model] if args.model else []), '--restricted', '--strict-mcp-config']
    quoted = [value for value in values if "'" in value]
    if quoted:
        sys.exit(f'pack-review: these arguments hold a single quote, which claude-code-action may split: {quoted}')
    print(' '.join(shlex.quote(value) for value in values))


if __name__ == '__main__':
    main()
