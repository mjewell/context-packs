#!/usr/bin/env python3
"""The claude_args the review hands claude-code-action, each as one line. A finder checks one unit of the packs, and
the merging agent merges the finders' answers with the pack-findings skill. Both get the schema their answer is
checked against, tools that only read, and the git server, which reads the change. claude-code-action splits the line
the way a shell would. Run, it prints the merging agent's line."""
import argparse
import json
from pathlib import Path
import shlex
import sys

REVIEW = Path(__file__).resolve().parent
# The diff and the repo's files can hold text written to steer the agent, so its tools only read: confined by
# --restricted to the checkout, without .git/config, where claude-code-action keeps its token, and to any folder it's
# given. It gets no shell, since an allowed git command such as git log --output=<file> writes any file. It reads the
# change through the git server instead, which runs fixed git commands, and that's its only MCP server, so nothing it
# does reaches the PR. It starts no subagents: the workflow starts one finder per unit, so no agent can skip one.
TOOLS = ['Read', 'Glob', 'Grep']
# Allows every tool on the git server. A name starting with mcp__github would make claude-code-action add its own
# GitHub servers.
SERVER = 'mcp__git'


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


def reading(base, head, model):
    """The arguments every agent that reads the change gets."""
    schema = json.loads((REVIEW / 'findings.schema.json').read_text(encoding='utf-8'))
    servers = {'mcpServers': {'git': {'type': 'stdio', 'command': sys.executable,
                                      'args': [str(REVIEW / 'git_server.py'), '--base', base, '--head', head]}}}
    return ['--json-schema', compact(schema), '--tools', ','.join(TOOLS), '--allowedTools', ','.join([*TOOLS, SERVER]),
            '--disallowedTools', 'Read(./.git/**)', *(['--model', model] if model else []), '--mcp-config',
            compact(servers), '--restricted', '--strict-mcp-config']


def finder(base, head, model):
    """A finder's line: its prompt holds everything it needs, so it gets no skill and no folder."""
    return line(reading(base, head, model))


def merger(inputs, base, head, model):
    """The merging agent's line: the pack-findings skill, and the folder holding the finders' answers."""
    return line(['--plugin-dir', str(REVIEW.parent), '--add-dir', inputs, *reading(base, head, model)])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', required=True, help="the folder holding docs.txt and the finders' answers")
    parser.add_argument('--base', required=True, help='the commit the reviewed change starts from')
    parser.add_argument('--head', required=True, help='the commit that is reviewed')
    parser.add_argument('--model', default='', help="the model to review with, if not Claude Code's default")
    args = parser.parse_args()
    print(merger(args.inputs, args.base, args.head, args.model))


if __name__ == '__main__':
    main()
