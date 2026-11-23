#!/usr/bin/env python3
"""The review's finders: one per unit, the instruction file then each pack's docs as `context-packs docs` lists
them, and the uncovered finder, which has no unit and reads the whole diff for choices no rule covers. `list` writes
their numbers as a step output, for the workflow's matrix to start each, so no agent decides whether a unit is worth
checking. `prompt` writes one finder's prompt and claude_args: the skill's prompt for its kind of finder, with the docs
it reads and the git server for the diff and log. `merge` writes the merging agent's, from the skill's merge prompt."""
import argparse
import json
from pathlib import Path
import sys

import args as claude

REVIEW = Path(__file__).resolve().parent
sys.path.insert(0, str(REVIEW.parent / 'src'))
from blocks import instructions  # noqa: E402  The CLI's own rule for which file holds the block.

PROMPTS = REVIEW.parent / 'skills' / 'pack-findings'
DIFF = "the git server's `diff` tool, one path at a time, for the paths its `changed` tool lists"
LOG = "the git server's `log` tool"
# What a finder in CI needs beyond its prompt, which a local subagent gets from the agent that starts it.
IN_CI = '''

You have no shell, and no way to read or write the pull request. `diff` starts each line the head has with its line \
number there: give that number as a spot's line, not a count of lines in the diff. Read every page of a \
path's diff before you judge it. Answer in the shape the output schema sets. '''
# What the merging agent in CI needs beyond the merge prompt.
MERGE_IN_CI = '''

You have no shell, and no way to read or write the pull request. The git server's `changed`, `diff` and `log` tools \
read the change, if a spot needs checking. Answer with groups, in the shape the output schema sets. Each group is one \
finding: the ids of the finders' findings it merges, and its kind, headline and take. Put every id in exactly one \
group. A script builds each finding's rules, spots, signs and exemplars from its group's findings.'''
# The sentence after it, for a unit's finder and for the uncovered finder.
RULE_KIND = 'Each rule with a deviating spot is one finding of kind `deviation`.'
UNCOVERED_KIND = 'Each choice is one finding of kind `uncovered choice`, with no rules.'


def units(docs):
    """Each unit's paths: the instruction file, then the docs each pack's table points at."""
    blocks = [block.splitlines() for block in Path(docs).read_text(encoding='utf-8').split('\n\n') if block.strip()]
    return [[instructions(Path('.')).name], *blocks]


def list_units(args):
    # The last unit is the uncovered one, which reads the whole diff for choices no rule covers.
    claude.output('units', json.dumps(list(range(len(units(args.docs)) + 1))))


def prompt(args):
    found = units(args.docs)
    if not 0 <= args.unit <= len(found):
        sys.exit(f'pack-review: there is no unit {args.unit}: the docs make {len(found) + 1} units.')
    # The number after the last unit's is the uncovered finder, which searches every doc for a rule that settles a
    # choice. The matrix calls it a unit too.
    uncovered = args.unit == len(found)
    paths = [path for unit in found for path in unit] if uncovered else found[args.unit]
    docs = ''.join(f'- `{path}`\n' for path in paths)
    name, kind = ('uncovered-prompt.md', UNCOVERED_KIND) if uncovered else ('unit-prompt.md', RULE_KIND)
    text = (PROMPTS / name).read_text(encoding='utf-8').format(diff=DIFF, log=LOG, docs=docs.rstrip('\n'))
    claude.output('prompt', text.rstrip('\n') + IN_CI + kind)
    claude.output('claude-args', claude.finder(args.base, args.head, args.model))


def sources(folder):
    """Every finder's findings, from the unit-<n>.json answers in folder, numbered as <finder>:<index>, so the merging
    agent can answer with ids and a script can build each finding from the ones it names."""
    answers = sorted(Path(folder).glob('unit-*.json'), key=lambda path: int(path.stem.split('-')[1]))
    return [{'id': f"{path.stem.split('-')[1]}:{n}", 'finding': finding} for path in answers
            for n, finding in enumerate(json.loads(path.read_text(encoding='utf-8'))['findings'])]


def merge(args):
    inputs = Path(args.inputs)
    (inputs / 'sources.json').write_text(json.dumps(sources(inputs), ensure_ascii=False), encoding='utf-8')
    answers = f"Every finder's findings are in `{inputs / 'sources.json'}`, each with an id."
    text = (PROMPTS / 'merge-prompt.md').read_text(encoding='utf-8').format(answers=answers)
    claude.output('prompt', text.rstrip('\n') + MERGE_IN_CI)
    claude.output('claude-args', claude.merger(args.inputs, args.base, args.head, args.model))


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
    third = commands.add_parser('merge', help="write the merging agent's prompt and claude_args as step outputs")
    third.add_argument('--inputs', required=True, help="the folder holding the finders' answers")
    third.add_argument('--base', required=True, help='the commit the reviewed change starts from')
    third.add_argument('--head', required=True, help='the commit that is reviewed')
    third.add_argument('--model', default='', help="the model to merge with, if not Claude Code's default")
    args = parser.parse_args()
    {'list': list_units, 'prompt': prompt, 'merge': merge}[args.command](args)


if __name__ == '__main__':
    main()
