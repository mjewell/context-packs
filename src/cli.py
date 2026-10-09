#!/usr/bin/env python3
"""Sync context packs into a repository, or into the workspace folder above the repositories: each pack's rules as a
block in AGENTS.md, after a header block explaining context packs, and each pack's required doc sets and the ones the
repository chose in docs/agents/packs/<pack>/."""
import argparse
import contextlib
import os
from pathlib import Path
import re
import shutil
import sys

import origins
from blocks import HEADER, HEADER_RULES, HEADER_START, block, region, snapshot
from packs import LOCAL, PACKS, Pack, Source, fetch


def sets(text):
    return {n for n in text.split(',') if n}


def apply(args, found):
    """The packs, and the optional doc sets each should have, once the command has run."""
    packs = list(found.packs)
    names = [p.name for p in packs]
    picked = {p.name: set(found.installed.get(p.name, [])) for p in packs}
    if args.command == 'add':
        if not re.fullmatch(r'[A-Za-z0-9._-]+', args.name) or args.name == HEADER:
            sys.exit(f'context-packs: {args.name} can\'t name a pack. '
                     'Use letters, digits, dots, dashes and underscores.')
        if args.name in names:
            sys.exit(f'context-packs: {args.repo} already has a pack named {args.name}.')
        if args.origin == LOCAL:
            if args.ref:
                sys.exit('context-packs: a pack in this repo syncs from its working tree, so it takes no --ref.')
            ref = None
        else:
            ref = origins.pin(args.origin, args.ref) if args.ref else origins.tip(args.origin)
        packs.append(Pack(args.name, args.origin, args.path, ref))
        picked[args.name] = sets(args.docs)
    named = [args.name] if args.command in ('remove', 'docs') else getattr(args, 'names', [])
    unknown = [n for n in named if n not in names]
    if unknown:
        sys.exit(f'context-packs: {args.repo} has no pack named {", ".join(unknown)}. '
                 f'Its packs: {", ".join(names) or "none"}.')
    if args.command == 'remove':
        packs = [p for p in packs if p.name != args.name]
    if args.command == 'docs':
        picked[args.name] = sets(args.sets)
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
    return packs, picked


def show(sources, picked):
    for source in sources:
        pack = source.pack
        print(f'{pack.name}  {pack.origin}' + f'  {pack.path}' * bool(pack.path) + f' @ {pack.ref}' * bool(pack.ref))
        for name in source.available():
            fields = source.front(name)
            if fields.get('tier') == 'required':
                print(f'  [x] {name} (required): {fields["when"]}')
            else:
                print(f'  [{"x" if name in picked[pack.name] else " "}] {name}: {fields["when"]}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('repo', type=Path)
    parser.add_argument('--workspace', action='store_true',
                        help='sync the folder above the repos, which gets no CLAUDE.md and needs no git repo')
    commands = parser.add_subparsers(dest='command', metavar='command',
                                     description='leave out the command to resync every pack at its pinned ref')
    add = commands.add_parser('add', help="install a pack, pinned to its origin's latest commit or to --ref")
    add.add_argument('name', help='what to call the pack in AGENTS.md and docs/agents/packs/')
    add.add_argument('origin', help='a git URL, or . for a folder in the synced repo itself')
    add.add_argument('--path', default='', help='the folder in the origin holding the pack, if not its root')
    add.add_argument('--ref', help='a tag or commit to pin the pack to')
    add.add_argument('--docs', default='', help='comma-separated optional doc sets to install')
    remove = commands.add_parser('remove', help='uninstall a pack')
    remove.add_argument('name')
    update = commands.add_parser('update', help='move pinned packs on: one pinned to a commit to the tip of its '
                                                "origin's default branch, one pinned to a release tag to the newest "
                                                'release in its series')
    update.add_argument('names', nargs='*', help='the packs to update; all of them if left out')
    update.add_argument('--ref', help='a tag or commit to pin the one named pack to instead')
    docs = commands.add_parser('docs', help="replace a pack's optional doc sets")
    docs.add_argument('name')
    docs.add_argument('sets', help="comma-separated optional doc sets, or '' for none")
    commands.add_parser('list', help='list the packs and their doc sets, marking the installed ones')
    args = parser.parse_args()
    repo = args.repo
    if not repo.is_dir():
        sys.exit(f'context-packs: {repo} is not a folder')
    if args.workspace and (repo / '.git').exists():
        sys.exit(f'context-packs: {repo} is a git repo. Sync it without --workspace.')
    if not args.workspace and not (repo / '.git').exists():
        sys.exit(f'context-packs: {repo} is not the root of a git repo. Pass the root of the repo to sync, '
                 'or --workspace for the folder above the repos.')

    found = region(repo)
    packs, picked = apply(args, found)

    with contextlib.ExitStack() as stack:
        sources = [Source(p, fetch(repo, p, stack)) for p in packs]
        if args.command == 'list':
            show(sources, picked)
            return

        claude_md = repo / 'CLAUDE.md'
        linked = claude_md.is_symlink() and os.readlink(claude_md) == 'AGENTS.md'
        if args.workspace and os.path.lexists(claude_md):
            sys.exit(f'context-packs: {claude_md} must not exist, or Claude Code would load the workspace\'s rules '
                     'inside every repo too. Delete it, then sync again.')
        if not args.workspace and not linked and os.path.lexists(claude_md):
            sys.exit(f'context-packs: {claude_md} must be a symlink to AGENTS.md, so every agent reads the same rules. '
                     'Move its contents into AGENTS.md, delete it, then sync again.')

        chosen = {}
        for source in sources:
            name = source.pack.name
            unknown = sorted(n for n in picked[name] if n not in source.available())
            if unknown:
                sys.exit(f'context-packs: {name} has no doc set named {", ".join(unknown)}. '
                         f'Available: {", ".join(source.available()) or "none"}. Choose from those with --docs.')
            chosen[name] = sorted(picked[name] | set(source.required()))
        bodies = {s.pack.name: s.body(chosen[s.pack.name]) for s in sources}
        starts = {s.pack.name: s.pack.start() for s in sources}

        for gone in {p.name for p in found.packs} - {p.name for p in packs}:
            if (repo / PACKS / gone).exists():
                shutil.rmtree(repo / PACKS / gone)
        blocks = [block(HEADER_START, HEADER_RULES)]
        for source in sources:
            synced = repo / source.pack.synced
            if synced.exists():
                shutil.rmtree(synced)
            for name in chosen[source.pack.name]:
                shutil.copytree(source.folder / name, synced / name)
            blocks.append(block(starts[source.pack.name], bodies[source.pack.name], snapshot(synced)))
        if (repo / PACKS).is_dir() and not any((repo / PACKS).iterdir()):
            (repo / PACKS).rmdir()
        text = found.text[:found.start] + '\n'.join(blocks) + found.text[found.end:]
        (repo / 'AGENTS.md').write_bytes(text.encode('utf-8'))
        if not args.workspace and not linked:
            claude_md.symlink_to('AGENTS.md')


if __name__ == '__main__':
    main()
