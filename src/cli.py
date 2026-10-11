#!/usr/bin/env python3
"""Sync context packs into a repository, or any folder such as the one above the repositories: each pack's rules as a
block in AGENTS.md, after a header block explaining context packs, and each pack's docs and the nested packs it
installs in docs/agents/packs/<pack>/."""
import argparse
import contextlib
import itertools
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sys

import origins
import report
from blocks import HEADER, HEADER_RULES, HEADER_START, block, region, snapshot
from packs import LOCAL, PACKS, Pack, fetch
import tree


def sets(text):
    return tuple(sorted({n for n in text.split(',') if n}))


def apply(args, found):
    """The packs, each with the optional nested packs it should have, once the command has run."""
    packs = list(found.packs)
    names = [p.name for p in packs]
    if args.command == 'add':
        if not re.fullmatch(r'[A-Za-z0-9._-]+', args.name) or args.name == HEADER:
            sys.exit(f'context-packs: {args.name} can\'t name a pack. '
                     'Use letters, digits, dots, dashes and underscores.')
        if args.name in names:
            sys.exit(f'context-packs: {args.dir} already has a pack named {args.name}.')
        if args.origin == LOCAL:
            if args.ref:
                sys.exit('context-packs: a pack in this repo syncs from its working tree, so it takes no --ref.')
            if args.docs:
                sys.exit('context-packs: a pack in this repo installs every nested pack it has, so it takes no --docs.')
            ref = None
        else:
            ref = origins.pin(args.origin, args.ref) if args.ref else origins.tip(args.origin)
        packs.append(Pack(args.name, args.origin, args.path, ref, sets(args.docs)))
    named = [args.name] if args.command in ('remove', 'docs') else getattr(args, 'names', [])
    unknown = [n for n in named if n not in names]
    if unknown:
        sys.exit(f'context-packs: {args.dir} has no pack named {", ".join(unknown)}. '
                 f'Its packs: {", ".join(names) or "none"}.')
    if args.command == 'remove':
        packs = [p for p in packs if p.name != args.name]
    if args.command == 'docs':
        i = names.index(args.name)
        if packs[i].local:
            sys.exit(f'context-packs: the {args.name} pack is in this repo, so it installs every nested pack it has. '
                     'Delete one to drop it.')
        packs[i] = packs[i]._replace(docs=sets(args.sets))
    if args.command == 'update':
        if args.ref and len(named) != 1:
            sys.exit('context-packs: --ref pins one pack, so name exactly one.')
        for i, pack in enumerate(packs):
            if pack.name not in (named or names):
                continue
            if pack.origin == LOCAL:
                if args.ref:
                    sys.exit(f'context-packs: the {pack.name} pack syncs from this repo\'s working tree, '
                             'so it takes no --ref.')
                continue
            packs[i] = pack._replace(ref=origins.pin(pack.origin, args.ref) if args.ref
                                     else origins.latest(pack.origin, pack.ref))
    # The folder inside would sync twice, maybe at another ref. Origins compare as written, so the same repo spelled
    # two ways gets past this.
    for a, b in itertools.combinations(packs, 2):
        outer, inner = sorted((PurePosixPath(a.path).parts, PurePosixPath(b.path).parts), key=len)
        if a.origin == b.origin and inner[:len(outer)] == outer:
            sys.exit(f'context-packs: the {a.name} and {b.name} packs overlap: one\'s folder in {a.origin} holds the '
                     'other\'s, so its rules would sync twice. Keep only one of them.')
    return packs


def show(packs, roots):
    """Each pack, then its nested packs as a tree, marking the installed ones and why each was installed if it
    wasn't picked."""
    for pack in packs:
        print(f'{pack.name}  {pack.origin}' + f'  {pack.path}' * bool(pack.path) + f' @ {pack.ref}' * bool(pack.ref))
        installed = tree.installs(roots[pack.name], pack)

        def lines(node, depth):
            for child in node.children:
                below = [p for p in pack.docs if p.startswith(f'{child.id}/')]
                why = (' (required)' if child.required else
                       f' (needed by {", ".join(below)})' if child.id in installed and child.id not in pack.docs
                       and not pack.local else '')
                when = f': {child.fields["when"]}' if 'when' in child.fields else ''
                print(f'{"  " * depth}[{"x" if child.id in installed else " "}] {child.id}{why}{when}')
                lines(child, depth + 1)
        lines(roots[pack.name], 1)


def main():
    parser = argparse.ArgumentParser(prog='context-packs', description=__doc__)
    parser.add_argument('--dir', type=Path, default=Path.cwd(),
                        help='the folder to sync, if not the current one')
    commands = parser.add_subparsers(dest='command', metavar='command',
                                     description='leave out the command to resync every pack at its pinned ref')
    add = commands.add_parser('add', help="install a pack, pinned to its origin's latest commit or to --ref")
    add.add_argument('name', help='what to call the pack in AGENTS.md and docs/agents/packs/')
    add.add_argument('origin', help='a git URL, or . for a folder in the synced repo itself')
    add.add_argument('--path', default='', help='the folder in the origin holding the pack, if not its root')
    add.add_argument('--ref', help='a tag or commit to pin the pack to')
    add.add_argument('--docs', default='', help='comma-separated optional nested packs to install')
    remove = commands.add_parser('remove', help='uninstall a pack')
    remove.add_argument('name')
    update = commands.add_parser('update', help='move pinned packs on: one pinned to a commit to the tip of its '
                                                "origin's default branch, one pinned to a release tag to the newest "
                                                'release in its series')
    update.add_argument('names', nargs='*', help='the packs to update; all of them if left out')
    update.add_argument('--ref', help='a tag or commit to pin the one named pack to instead')
    docs = commands.add_parser('docs', help="replace a pack's optional nested packs")
    docs.add_argument('name')
    docs.add_argument('sets', help="comma-separated optional nested packs, or '' for none")
    commands.add_parser('list', help='list the packs and their nested packs, marking the installed ones')
    args = parser.parse_args()
    repo = args.dir
    if not repo.is_dir():
        sys.exit(f'context-packs: {repo} is not a folder')

    found = region(repo)
    packs = apply(args, found)

    with contextlib.ExitStack() as stack:
        folders = {p.name: fetch(repo, p, stack) for p in packs}
        roots = {p.name: tree.load(folders[p.name], p) for p in packs}
        if args.command == 'list':
            show(packs, roots)
            return

        claude_md = repo / 'CLAUDE.md'
        linked = claude_md.is_symlink() and os.readlink(claude_md) == 'AGENTS.md'
        if not linked and os.path.lexists(claude_md):
            sys.exit(f'context-packs: {claude_md} must be a symlink to AGENTS.md, so every agent reads the same rules. '
                     'Move its contents into AGENTS.md, delete it, then sync again.')

        installed = {p.name: tree.installs(roots[p.name], p) for p in packs}

        for gone in {p.name for p in found.packs} - {p.name for p in packs}:
            if (repo / PACKS / gone).exists():
                shutil.rmtree(repo / PACKS / gone)
        blocks = {HEADER: block(HEADER_START, HEADER_RULES)}
        for pack in packs:
            root = roots[pack.name]
            generated = repo / PACKS / pack.name
            if generated.exists():
                shutil.rmtree(generated)
            tree.write(root, pack, installed[pack.name], folders[pack.name], repo)
            blocks[pack.name] = block(pack.start(), tree.render(root, pack, installed[pack.name]),
                                      snapshot(generated))
        if (repo / PACKS).is_dir() and not any((repo / PACKS).iterdir()):
            (repo / PACKS).rmdir()
        text = found.text[:found.start] + '\n'.join(blocks.values()) + found.text[found.end:]
        created = not (repo / 'AGENTS.md').exists()
        (repo / 'AGENTS.md').write_bytes(text.encode('utf-8'))
        if not linked:
            claude_md.symlink_to('AGENTS.md')
        for line in report.changes(found, packs, blocks, created, linked):
            print(line)


if __name__ == '__main__':
    main()
