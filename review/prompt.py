#!/usr/bin/env python3
"""Print the prompt the review workflow hands one of its agents, as a step output for $GITHUB_OUTPUT. `unit` runs the
pack-findings skill on one unit of docs, whose paths from the checkout stdin holds as a JSON list. `merge` runs it on
the units' answers. A review asked to read every doc read only those whose `when` matched the diff, so a unit's prompt
says the tables' routing doesn't apply. It names the docs without their text: runs given the text skipped the docs."""
import argparse
import json
import secrets
import sys

ROUTING = ("The tables' rule to read a doc only when its row matches the work doesn't apply to this review: check the "
           'diff against every doc, whatever its `when` says.')


def unit(base, head, inputs, docs):
    listed = '\n'.join(f'- `{doc}`' for doc in docs)
    return '\n\n'.join([f'/context-packs:pack-findings ci-unit {base}...{head} {inputs}', ROUTING,
                        f'Your unit is these docs. Read each one in full:\n\n{listed}'])


def merge(base, head, inputs):
    return f'/context-packs:pack-findings ci-merge {base}...{head} {inputs}'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['unit', 'merge'])
    parser.add_argument('--base', required=True, help='the commit the PR merges into')
    parser.add_argument('--head', required=True, help='the commit under review, checked out here')
    parser.add_argument('--inputs', required=True, help='the folder holding the diff and log the agent reviews')
    args = parser.parse_args()
    text = (unit(args.base, args.head, args.inputs, json.loads(sys.stdin.read())) if args.mode == 'unit'
            else merge(args.base, args.head, args.inputs))
    # A delimiter no path can guess, so no line the PR's tables control ends the value and sets another output.
    delimiter = secrets.token_hex(16)
    print(f'prompt<<{delimiter}\n{text}\n{delimiter}')


if __name__ == '__main__':
    main()
