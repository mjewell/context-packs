#!/usr/bin/env python3
"""The review's units, one per finder: the instruction file, then each pack's docs as `context-packs docs` lists
them. `list` writes their numbers as a step output, for the workflow's matrix to start one finder each, so no agent
decides whether a unit is worth checking. `prompt` writes one finder's prompt and claude_args: the skill's unit
prompt, with the unit's docs and the git server for the diff and log."""
import argparse
import json
from pathlib import Path
import sys

import args as claude
from pairing import output

REVIEW = Path(__file__).resolve().parent
sys.path.insert(0, str(REVIEW.parent / 'src'))
from blocks import instructions  # noqa: E402  The CLI's own rule for which file holds the block.

PROMPT = REVIEW.parent / 'skills' / 'pack-findings' / 'unit-prompt.md'
DIFF = "the git server's `diff` tool, one path at a time, for the paths its `changed` tool lists"
LOG = "the git server's `log` tool"
# What a finder in CI needs beyond the unit prompt, which a local subagent gets from the agent that starts it.
IN_CI = '''

You have no shell, and no way to read or write the pull request. `diff` starts each line the head has with its line \
number there: give that number as a spot's line, not a count of lines in the diff. Read every page of a \
path's diff before you judge it. Answer in the shape the output schema sets: each rule with a deviating spot is one \
finding of kind `deviates`.'''


def units(docs):
    """Each unit's paths: the instruction file, then the docs each pack's table points at."""
    blocks = [block.split() for block in Path(docs).read_text(encoding='utf-8').split('\n\n') if block.strip()]
    return [[instructions(Path('.')).name], *blocks]


def list_units(args):
    output('units', json.dumps(list(range(len(units(args.docs))))))


def prompt(args):
    found = units(args.docs)
    if not 0 <= args.unit < len(found):
        sys.exit(f'pack-review: there is no unit {args.unit}: the docs make {len(found)} units.')
    docs = ''.join(f'- `{path}`\n' for path in found[args.unit])
    text = PROMPT.read_text(encoding='utf-8').format(diff=DIFF, log=LOG, docs=docs.rstrip('\n'))
    output('prompt', text.rstrip('\n') + IN_CI)
    output('claude-args', claude.finder(args.base, args.head, args.model))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    first = commands.add_parser('list', help="write the units' numbers as a step output")
    first.add_argument('--docs', required=True, help='what `context-packs docs` printed')
    second = commands.add_parser('prompt', help="write one finder's prompt and claude_args as step outputs")
    second.add_argument('--docs', required=True, help='what `context-packs docs` printed')
    second.add_argument('--unit', type=int, required=True, help="the unit's number, from list")
    second.add_argument('--base', required=True, help='the commit the reviewed change starts from')
    second.add_argument('--head', required=True, help='the commit that is reviewed')
    second.add_argument('--model', default='', help="the model to check with, if not Claude Code's default")
    args = parser.parse_args()
    {'list': list_units, 'prompt': prompt}[args.command](args)


if __name__ == '__main__':
    main()
