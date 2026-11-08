#!/usr/bin/env python3
"""Print the prompt the review action hands claude-code-action, as a step output for $GITHUB_OUTPUT: the pack-findings
skill with its arguments, then the units of docs for its subagents. stdin holds the docs' paths from the checkout as
`context-packs docs` prints them, with a blank line between packs. A review asked to read every doc read only those
whose `when` matched the diff, so the prompt says the tables' routing doesn't apply. It names the docs without their
text: runs given the text skipped the docs, and runs given the units split them across subagents that read them."""
import argparse
import secrets
import sys

ROUTING = ("The tables' rule to read a doc only when its row matches the work doesn't apply to this review: check the "
           'diff against every doc, whatever its `when` says.')
SPLIT = ("Check each of these units in its own subagent, even when there's only one. A subagent doesn't see this "
         "prompt, so give it its unit's paths, and tell it to read each of its docs in full, whatever its `when` says.")


def prompt(base, head, inputs, units):
    listed = ["- Unit 1: the instruction file's own rules, and any doc it points at outside the context-packs block"]
    listed += [f'- Unit {n}: ' + ', '.join(f'`{doc}`' for doc in unit) for n, unit in enumerate(units, 2)]
    return '\n\n'.join([f'/context-packs:pack-findings ci {base}...{head} {inputs}', ROUTING, SPLIT, '\n'.join(listed)])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', required=True, help='the commit the PR merges into')
    parser.add_argument('--head', required=True, help='the commit under review, checked out here')
    parser.add_argument('--inputs', required=True, help='the folder holding the diff and log the agent reviews')
    args = parser.parse_args()
    units = [unit.splitlines() for unit in sys.stdin.read().split('\n\n') if unit.strip()]
    # A delimiter no path can guess, so no line the PR's tables control ends the value and sets another output.
    delimiter = secrets.token_hex(16)
    print(f'prompt<<{delimiter}\n{prompt(args.base, args.head, args.inputs, units)}\n{delimiter}')


if __name__ == '__main__':
    main()
