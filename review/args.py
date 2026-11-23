#!/usr/bin/env python3
"""The claude_args the review hands claude-code-action, as one line. The reviewer runs the pack-findings skill, whose
wizard starts the finders and the merge. claude-code-action splits the line the way a shell would. output() writes a
prompt or a claude_args line as a GitHub step output."""
import json
import os
from pathlib import Path
import shlex
import sys
import uuid

REVIEW = Path(__file__).resolve().parent


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


def reviewer(answers, model):
    """The review agent's line: it runs the pack-findings skill, as a local review does, from this checkout of the
    review, with this checkout's CLI. It may run only the commands the skill runs, and has no MCP server. It writes
    only in answers, the folder where the wizard's briefs say to write each answer."""
    # The path the skill builds from its own folder, so the agent's commands match it.
    cli = f'python3 {REVIEW.parent}/src/cli.py'
    # git rev-parse and git status have no option that writes a file, unlike git log's --output.
    allowed = ['Skill(context-packs:pack-findings)', f'Bash({cli} review:*)', f'Bash({cli} docs)',
               'Bash(git rev-parse:*)', 'Bash(git status:*)',
               # A headless run writes outside its working directory only with both this rule and --add-dir. The
               # rule's // makes the path absolute, where one / would start from the settings file.
               f'Edit(/{answers}/**)']
    return line(['--plugin-dir', str(REVIEW.parent), '--add-dir', answers,
                 '--tools', 'Read,Glob,Grep,Write,Bash,Agent,Skill',
                 '--allowedTools', ','.join(allowed), '--disallowedTools', 'Read(./.git/**)',
                 *(['--model', model] if model else []), '--restricted', '--strict-mcp-config'])
