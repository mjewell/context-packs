#!/usr/bin/env python3
"""Tools for spec trees, as the spec beside this folder, ../spec.md, defines them.

Usage:
  python3 scripts/trees.py check
  python3 scripts/trees.py stats
  python3 scripts/trees.py links-to <id>
  python3 scripts/trees.py render <id>.tree.md [-o out.html]

Standard library only."""
import argparse
import sys
from pathlib import Path

from tree_check import check, links_to, stats
from tree_model import parse
from tree_render import page

def run_check(args):
    """Prints each problem in the repo's trees, and exits 1 when any fails."""
    repo = repo_root(Path.cwd())
    problems = check(repo)
    for file, level, message in problems:
        print(f'{file.relative_to(repo)}: {level}: {message}')
    sys.exit(1 if any(level == 'fail' for _, level, _ in problems) else 0)


def run_stats(args):
    print('\n'.join(stats(repo_root(Path.cwd()))))


def run_links_to(args):
    repo = repo_root(Path.cwd())
    links = links_to(repo, args.id)
    if links is None:
        sys.exit(f'trees.py: no node has the ID {args.id}')
    for file, text in links:
        print(f'{file.relative_to(repo)}: {text}')


def render(args):
    """Writes the page beside the tree's file, as <id>.tree.html, unless the tree doesn't read as a tree."""
    path = args.tree.resolve()
    tree = parse(path)
    if tree.problems:
        sys.exit('\n'.join(f'trees.py: {file}: {message}' for file, message in tree.problems))
    out = args.out or path.with_suffix('.html')
    out.write_text(page(tree), encoding='utf-8')
    print(out)


def repo_root(path):
    """The nearest folder at or above path holding `.git`, which is a file in a worktree and a folder otherwise."""
    for folder in [path, *path.parents]:
        if (folder / '.git').exists():
            return folder
    sys.exit(f'trees.py: {path} is not in a git repo')


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('check', help="check every tree in the repo against the spec's rules").set_defaults(run=run_check)
    commands.add_parser('stats', help='print the size of each view').set_defaults(run=run_stats)
    links = commands.add_parser('links-to', help='list the nodes that link to an ID')
    links.add_argument('id')
    links.set_defaults(run=run_links_to)
    r = commands.add_parser('render', help='write a tree as one HTML page')
    r.add_argument('tree', type=Path)
    r.add_argument('-o', '--out', type=Path, help='default: <id>.tree.html beside the tree file')
    r.set_defaults(run=render)
    args = parser.parse_args()
    args.run(args)


if __name__ == '__main__':
    main()
