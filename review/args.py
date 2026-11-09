#!/usr/bin/env python3
"""Print, on one line, the claude_args the review workflow hands claude-code-action for one agent: the pack-findings
skill, the schema its answer is checked against, and tools that only read the checkout and the folder holding the diff
and log. A unit's agent answers with its deviations and the rules it found followed, and the merge agent with the
conflicts and uncovered choices. Both answers are built from findings.schema.json, so a finding has one shape.
claude-code-action splits the line the way a shell would."""
import argparse
import json
from pathlib import Path
import shlex
import sys

REVIEW = Path(__file__).resolve().parent
# The diff and the repo's files can hold text written to steer the agent, so its tools only read:
# confined by --restricted to the checkout, without .git/config, where claude-code-action keeps its token, and to
# the folder the workflow wrote the diff and log to. It gets no shell, since an allowed git command such as
# git log --output=<file> writes any file, and no MCP servers, so nothing it does reaches the PR. No agent splits its
# work, since each unit of docs already has its own.
TOOLS = ['Read', 'Glob', 'Grep']


def compact(value):
    """JSON on one line, with each ' written as \\u0027 so the whole value fits in one pair of single quotes."""
    return json.dumps(value, separators=(',', ':')).replace("'", '\\u0027')


def kinds(finding, enum):
    """The finding's schema, with its kind narrowed to enum."""
    return {**finding, 'properties': {**finding['properties'], 'kind': {'enum': enum}}}


def answer(name):
    findings = json.loads((REVIEW / 'findings.schema.json').read_text(encoding='utf-8'))
    finding = findings['properties']['findings']['items']
    if name == 'merge':
        return {**findings, 'properties': {'findings': {**findings['properties']['findings'],
                                                        'items': kinds(finding, ['conflicting', 'uncovered'])}}}
    followed = {'type': 'object', 'additionalProperties': False, 'required': ['rule', 'spots'],
                'properties': {'rule': finding['properties']['rules']['items'],
                               'spots': finding['properties']['spots']}}
    return {'type': 'object', 'additionalProperties': False, 'required': ['deviations', 'followed'], 'properties': {
        'deviations': {'type': 'array', 'description': 'Each rule of the unit the change deviates from, as a finding.',
                       'items': kinds(finding, ['deviates'])},
        'followed': {'type': 'array', 'items': followed,
                     'description': 'Each rule of the unit that applies to the change, which every spot follows.'}}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--answer', choices=['unit', 'merge'], required=True, help="which agent's answer to check")
    parser.add_argument('--inputs', required=True, help='the folder holding the diff and log the agent reviews')
    parser.add_argument('--model', default='', help="the model to review with, if not Claude Code's default")
    args = parser.parse_args()
    values = ['--plugin-dir', str(REVIEW.parent), '--json-schema', compact(answer(args.answer)), '--tools', ','.join(TOOLS),
              '--allowedTools', ','.join(TOOLS), '--add-dir', args.inputs, '--disallowedTools', 'Read(./.git/**)',
              *(['--model', args.model] if args.model else []), '--restricted', '--strict-mcp-config']
    quoted = [value for value in values if "'" in value]
    if quoted:
        sys.exit(f'pack-review: these arguments hold a single quote, which claude-code-action may split: {quoted}')
    print(' '.join(shlex.quote(value) for value in values))


if __name__ == '__main__':
    main()
