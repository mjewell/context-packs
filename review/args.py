#!/usr/bin/env python3
"""Print, on one line, the claude_args the review action hands claude-code-action: the pack-findings skill, the schema
the agent's answer is checked against, tools that only read the checkout and the folder holding docs.txt, and the git
server, which reads the change. claude-code-action splits the line the way a shell would."""
import argparse
import json
from pathlib import Path
import shlex
import sys

REVIEW = Path(__file__).resolve().parent
# The diff and the repo's files can hold text written to steer the agent, so its tools only read:
# confined by --restricted to the checkout, without .git/config, where claude-code-action keeps its token, and to
# the folder the action wrote docs.txt to. It gets no shell, since an allowed git command such as
# git log --output=<file> writes any file. It reads the change through the git server instead, which runs fixed git
# commands, and that's its only MCP server, so nothing it does reaches the PR.
TOOLS = ['Read', 'Glob', 'Grep', 'Agent']
# Allows every tool on the git server. A name starting with mcp__github would make claude-code-action add its own
# GitHub servers.
SERVER = 'mcp__git'

# Subagents run in the background unless this is set, so the agent can answer before they've reported, and the answer
# misses their findings.
SETTINGS = {'env': {'CLAUDE_CODE_DISABLE_BACKGROUND_TASKS': '1'}}


def compact(value):
    """JSON on one line, with each ' written as \\u0027 so the whole value fits in one pair of single quotes."""
    return json.dumps(value, separators=(',', ':')).replace("'", '\\u0027')


def line(values):
    """The values as one claude_args line, each quoted whole. A value holding a single quote stops the run, since
    claude-code-action may split it."""
    quoted = [value for value in values if "'" in value]
    if quoted:
        sys.exit(f'pack-review: these arguments hold a single quote, which claude-code-action may split: {quoted}')
    return ' '.join(shlex.quote(value) for value in values)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', required=True, help='the folder holding docs.txt')
    parser.add_argument('--base', required=True, help='the commit the reviewed change starts from')
    parser.add_argument('--head', required=True, help='the commit that is reviewed')
    parser.add_argument('--model', default='', help="the model to review with, if not Claude Code's default")
    args = parser.parse_args()
    schema = json.loads((REVIEW / 'findings.schema.json').read_text(encoding='utf-8'))
    servers = {'mcpServers': {'git': {'type': 'stdio', 'command': sys.executable,
                                      'args': [str(REVIEW / 'git_server.py'), '--base', args.base, '--head', args.head]}}}
    values = ['--plugin-dir', str(REVIEW.parent), '--json-schema', compact(schema), '--tools', ','.join(TOOLS),
              '--allowedTools', ','.join([*TOOLS, SERVER]), '--add-dir', args.inputs,
              '--disallowedTools', 'Read(./.git/**)', '--settings', compact(SETTINGS),
              *(['--model', args.model] if args.model else []), '--mcp-config', compact(servers), '--restricted',
              '--strict-mcp-config']
    print(line(values))


if __name__ == '__main__':
    main()
