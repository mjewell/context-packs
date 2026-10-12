#!/usr/bin/env python3
"""Sync context packs into a repository, or any folder such as the one above the repositories: each pack's rules as a
block in AGENTS.md, after a header block explaining context packs, and each pack's docs and the indexes of the packs
nested in it in docs/agents/packs/<pack>/."""
import argparse
import contextlib
import itertools
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sys

import evaluate
import imports
import origins
import report
import sync
from blocks import HEADER, instructions, region
from packs import PACKS, Pack, fetch, local
import tree


def apply(args, found, imported):
    """The packs in AGENTS.md once the command has run, with imported the names of the import packs, which
    imports.apply changes."""
    packs = list(found.packs)
    names = [p.name for p in packs]
    if args.command == 'add':
        if not re.fullmatch(r'[A-Za-z0-9._-]+', args.name) or args.name == HEADER:
            sys.exit(f'context-packs: {args.name} can\'t name a pack. '
                     'Use letters, digits, dots, dashes and underscores.')
        if args.into:
            return packs
        if args.name in names:
            sys.exit(f'context-packs: {args.dir} already has a pack named {args.name}.')
        if local(args.origin):
            if args.ref:
                sys.exit(f'context-packs: {args.origin} is a folder on disk, which syncs from its working tree, so '
                         'it takes no --ref.')
            ref = None
        else:
            ref = origins.pin(args.origin, args.ref) if args.ref else origins.tip(args.origin)
        packs.append(Pack(args.name, args.origin, args.path, ref))
    named = [args.name] if args.command in ('remove', 'eval') else getattr(args, 'names', [])
    unknown = [n for n in named if n not in names + imported]
    if unknown:
        sys.exit(f'context-packs: {args.dir} has no pack named {", ".join(unknown)}. '
                 f'Its packs: {", ".join(names + imported) or "none"}.')
    if args.command == 'remove':
        packs = [p for p in packs if p.name != args.name]
    if args.command == 'update':
        if args.ref and len(named) != 1:
            sys.exit('context-packs: --ref pins one pack, so name exactly one.')
        for i, pack in enumerate(packs):
            if pack.name not in (named or names):
                continue
            if pack.local:
                if args.ref:
                    sys.exit(f'context-packs: the {pack.name} pack syncs from the working tree of {pack.origin}, '
                             'so it takes no --ref.')
                continue
            packs[i] = pack._replace(ref=origins.pin(pack.origin, args.ref) if args.ref
                                     else origins.latest(pack.origin, pack.ref))
    return packs


def check(packs):
    """Stop unless every pack, import packs included, has a name of its own and a folder no other holds."""
    names = [p.name for p in packs]
    for name in sorted({n for n in names if names.count(n) > 1}):
        sys.exit(f'context-packs: more than one pack is named {name}, counting import packs. Commands name a pack '
                 'alone, so rename one.')
    # The folder inside would sync twice, maybe at another ref. Origins compare as written, so the same repo spelled
    # two ways gets past this.
    for a, b in itertools.combinations(packs, 2):
        outer, inner = sorted((PurePosixPath(a.path).parts, PurePosixPath(b.path).parts), key=len)
        if a.origin == b.origin and inner[:len(outer)] == outer:
            sys.exit(f'context-packs: the {a.name} and {b.name} packs overlap: one\'s folder in {a.origin} holds the '
                     'other\'s, so its rules would sync twice. Keep only one of them.')


def show(packs, known):
    """Each pack: its name, where it comes from, and its pin, with its import packs under it."""
    def line(pack):
        return f'{pack.name}  {pack.origin}' + f'  {pack.path}' * bool(pack.path) + f' @ {pack.ref}' * bool(pack.ref)
    for pack in packs:
        print(line(pack))
        for imported in known:
            if imported.holder == pack.name:
                print(f'  {line(imported.pack)}')


def main():
    parser = argparse.ArgumentParser(prog='context-packs', description=__doc__)
    parser.add_argument('--dir', type=Path, default=Path.cwd(),
                        help='the folder to sync, if not the current one')
    commands = parser.add_subparsers(dest='command', metavar='command',
                                     description='leave out the command to resync every pack at its pinned ref')
    add = commands.add_parser('add', help="install a pack, pinned to its origin's latest commit or to --ref")
    add.add_argument('name', help='what to call the pack in AGENTS.md and docs/agents/packs/')
    add.add_argument('origin', help='a git URL, or the path of a folder on disk: . for the synced repo itself, or one '
                                    'beside it such as ../agent-config')
    add.add_argument('--path', default='', help='the folder in the origin holding the pack, if not its root')
    add.add_argument('--ref', help='a tag or commit to pin the pack to')
    add.add_argument('--into', help='import the pack into the pack read from this folder on disk, as an import pack '
                                    'at <folder>/<name>/pack.md, instead of installing it in AGENTS.md')
    add.add_argument('--when', help="the import pack's when, which gives it a row; without one, it's pasted in")
    remove = commands.add_parser('remove', help='uninstall a pack')
    remove.add_argument('name')
    update = commands.add_parser('update', help='move pinned packs on: one pinned to a commit to the tip of its '
                                                "origin's default branch, one pinned to a release tag to the newest "
                                                'release in its series')
    update.add_argument('names', nargs='*', help='the packs to update; all of them if left out')
    update.add_argument('--ref', help='a tag or commit to pin the one named pack to instead')
    commands.add_parser('list', help='list the packs, where each comes from, and its pin')
    evals = commands.add_parser('eval', help="run a pack's eval cases with each doc, and again without it, through "
                                             'claude plugin eval; pass it options after --')
    evals.add_argument('name', help='the pack, by its name in AGENTS.md')
    evals.add_argument('doc', nargs='?', help='the doc whose cases to run, by its path in the pack without .md; '
                                              'every doc with cases if left out')
    argv = sys.argv[1:]
    split = argv.index('--') if '--' in argv else len(argv)
    args, options = parser.parse_args(argv[:split]), argv[split + 1:]
    if split < len(argv) and args.command != 'eval':
        parser.error('only eval takes options after --, which it passes to claude plugin eval')
    repo = args.dir
    if not repo.is_dir():
        sys.exit(f'context-packs: {repo} is not a folder')

    file = instructions(repo)
    found = region(repo, file)
    before = imports.find(repo, found.packs)
    packs = apply(args, found, [i.pack.name for i in before])
    known, edits = imports.apply(args, repo, packs, imports.find(repo, packs))
    check(packs + [i.pack for i in known])

    with contextlib.ExitStack() as stack:
        folders = {p.name: fetch(repo, p, stack) for p in packs}
        imported = {p.name: {} for p in packs if p.local}
        for i in known:
            source = fetch(repo, i.pack, stack)
            fields, rules = i.front()
            root = tree.load(source, i.pack)
            root = root._replace(fields=fields, rules='\n'.join(r for r in (rules, root.rules) if r))
            imported[i.holder][i.id] = tree.Imported(i.id, i.pack, root, source)
        roots = {p.name: tree.load(folders[p.name], p, imported=imported.get(p.name)) for p in packs}
        if args.command == 'list':
            show(packs, known)
            return
        if args.command == 'eval':
            evaluate.evaluate(repo, file, found, packs, folders, args.name, args.doc, options)
            return

        for gone in {p.name for p in found.packs} - {p.name for p in packs}:
            if (repo / PACKS / gone).exists():
                shutil.rmtree(repo / PACKS / gone)
        text, blocks = sync.write(repo, found, packs, folders, roots)
        for pack_md, pack_md_text in edits:
            if pack_md_text is None:
                shutil.rmtree(repo / pack_md.parent)
            else:
                (repo / pack_md).parent.mkdir(parents=True, exist_ok=True)
                (repo / pack_md).write_text(pack_md_text, encoding='utf-8')
        created = not file.exists()
        file.write_bytes(text.encode('utf-8'))
        # A new AGENTS.md gets CLAUDE.md linked to it, so Claude Code reads it too. A repo that already has its own
        # instruction files keeps them as they are.
        link = created and not os.path.lexists(repo / 'CLAUDE.md')
        if link:
            (repo / 'CLAUDE.md').symlink_to('AGENTS.md')
        for line in report.changes(found, packs, blocks, created, link, before, known):
            print(line)


if __name__ == '__main__':
    main()
