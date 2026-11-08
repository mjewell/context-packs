"""The files a synced folder's tables point an agent at, read from the synced files alone, so listing them fetches no
pack from git."""
from pathlib import Path
import re
import sys

from blocks import read
from packs import base

# A table as tree.table writes it, and the path in each of its rows.
TABLE = re.compile(r'^\| When \| Read \|\n\|---\|---\|\n((?:\|.*\|\n)*)', re.M)
ROW = re.compile(r'^\| .* \| `([^`]+)` \|$', re.M)


def units(repo, block):
    """The paths the block's tables point at, then those the tables in each of those files point at, as the tables
    show them, grouped by the table they're in. Each table is one pack's, so each group is a unit for the review to
    check. A nested pack's index holds that pack's own rules, so it starts its own table's group, not its parent's."""
    start = base(repo)
    # The tables' paths start from the root of the git repo holding the folder, unless they're absolute.
    root = repo.resolve().parents[len(start.parts) - 1] if start.parts and not start.is_absolute() else repo.resolve()
    found, seen, queue = [], set(), [(None, block)]
    while queue:
        index, text = queue.pop(0)
        for n, table in enumerate(TABLE.findall(text)):
            unit = [index] if index and n == 0 else []
            for path in ROW.findall(table):
                if path in seen:
                    continue
                seen.add(path)
                file = root / path
                if not file.is_file():
                    sys.exit(f"context-packs: a table points at {path}, which doesn't exist. Run `npx context-packs` "
                             'and commit the result.')
                content = read(file)
                if TABLE.search(content):
                    queue.append((path, content))
                else:
                    unit.append(path)
            if unit:
                found.append(unit)
    return found
