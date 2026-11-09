#!/usr/bin/env python3
"""Print the units the review checks in parallel, as the matrix for the review workflow's unit jobs, a step output for
$GITHUB_OUTPUT. The first unit is the instruction file, for its own rules and any doc it points at outside the
context-packs block. Each after it is one pack's docs: stdin holds them as `context-packs docs` prints them, with a
blank line between packs. Run it in the checkout."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))
from blocks import instructions  # noqa: E402  The sync's rule for which file holds the packs, in its one home.


def main():
    file = instructions(Path('.'))
    if not file.is_file():
        sys.exit('pack-review: the repo has no AGENTS.md or CLAUDE.md, so it has no packs to review against. Run '
                 '`npx context-packs` and commit the result.')
    packs = [pack.splitlines() for pack in sys.stdin.read().split('\n\n') if pack.strip()]
    units = [[file.as_posix()], *packs]
    # JSON on one line, so no path the PR's tables control can end the value and set another output.
    print('matrix=' + json.dumps({'include': [{'unit': n, 'docs': docs} for n, docs in enumerate(units, 1)]}))


if __name__ == '__main__':
    main()
