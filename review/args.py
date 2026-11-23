#!/usr/bin/env python3
"""The claude_args the review hands claude-code-action, as one line, and the schemas the wizard checks answers
against. The reviewer runs the pack-findings skill, whose wizard starts the finders and the merge. claude-code-action
splits the line the way a shell would. output() writes a prompt or a claude_args line as a GitHub step output."""
import json
import os
from pathlib import Path
import shlex
import sys
import uuid

REVIEW = Path(__file__).resolve().parent
# The schema lives with the pack-findings skill, so a local review and CI read one copy.
SCHEMA = REVIEW.parent / 'skills' / 'pack-findings' / 'findings.schema.json'


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


def output(name, value):
    """Write a step output, under a delimiter the value can't hold."""
    delimiter = f'EOF_{uuid.uuid4().hex}'
    assert delimiter not in value
    with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as out:
        out.write(f'{name}<<{delimiter}\n{value}\n{delimiter}\n')


def findings_schema():
    return json.loads(SCHEMA.read_text(encoding='utf-8'))


def groups_schema():
    """The merging agent's answer: which of the finders' findings make each finding, with its kind, headline and take,
    from the findings schema. A script builds the rest of each finding from its group's findings."""
    finding = findings_schema()['properties']['findings']['items']['properties']
    group = {'type': 'object', 'additionalProperties': False, 'required': ['ids', 'kind', 'headline', 'take'],
             'properties': {'ids': {'type': 'array', 'minItems': 1, 'items': {'type': 'string'},
                                    'description': "The ids of the finders' findings this one merges."},
                            'kind': finding['kind'], 'headline': finding['headline'], 'take': finding['take']}}
    return {'type': 'object', 'additionalProperties': False, 'required': ['groups'],
            'properties': {'groups': {'type': 'array', 'items': group}}}


def reviewer(model):
    """The review agent's line: it runs the pack-findings skill, as a local review does, from this checkout of the
    review, with this checkout's CLI. It may run only the commands the skill runs, and has no MCP server. It reads and
    writes files only in the checkout and in its scratchpad, where it writes its answers before passing them to the
    wizard."""
    # The path the skill builds from its own folder, so the agent's commands match it.
    cli = f'python3 {REVIEW.parent}/src/cli.py'
    # git rev-parse and git status have no option that writes a file, unlike git log's --output.
    allowed = ['Skill(context-packs:pack-findings)', f'Bash({cli} review:*)', f'Bash({cli} docs)',
               'Bash(git rev-parse:*)', 'Bash(git status:*)']
    return line(['--plugin-dir', str(REVIEW.parent), '--tools', 'Read,Glob,Grep,Write,Bash,Agent,Skill',
                 '--allowedTools', ','.join(allowed), '--disallowedTools', 'Read(./.git/**)',
                 *(['--model', model] if model else []), '--restricted', '--strict-mcp-config'])
