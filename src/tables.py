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


def rows(text):
    return [path for table in TABLE.findall(text) for path in ROW.findall(table)]


def pointed(repo, block):
    """Every path the block's tables point at, then those the tables in each of those files point at, as the tables
    show them."""
    start = base(repo)
    # The tables' paths start from the root of the git repo holding the folder, unless they're absolute.
    root = repo.resolve().parents[len(start.parts) - 1] if start.parts and not start.is_absolute() else repo.resolve()
    found, queue = [], rows(block)
    while queue:
        path = queue.pop(0)
        if path in found:
            continue
        found.append(path)
        file = root / path
        if not file.is_file():
            sys.exit(f"context-packs: a table points at {path}, which doesn't exist. Run `npx context-packs` and "
                     'commit the result.')
        queue += rows(read(file))
    return found
