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

import imports
import report
from blocks import HEADER, HEADER_RULES, HEADER_START, block, instructions, region, snapshot
from packs import PACKS, fetch
import tree


def apply(args, found, imported):
    """The markers' packs once the command has run, after checking that the packs it names exist, with imported the
    names of the import packs held in packs. imports.apply then adds packs and moves pins."""
    packs = list(found.packs)
    names = [p.name for p in packs]
    if args.command == 'add':
        if not re.fullmatch(r'[A-Za-z0-9._-]+', args.name) or args.name == HEADER:
            sys.exit(f'context-packs: {args.name} can\'t name a pack. '
                     'Use letters, digits, dots, dashes and underscores.')
        if args.name in names + imported:
            sys.exit(f'context-packs: {args.dir} already has a pack named {args.name}.')
    named = [args.name] if args.command == 'remove' else getattr(args, 'names', [])
    unknown = [n for n in named if n not in names + imported]
    if unknown:
        sys.exit(f'context-packs: {args.dir} has no pack named {", ".join(unknown)}. '
                 f'Its packs: {", ".join(names + imported) or "none"}.')
    if args.command == 'remove':
        packs = [p for p in packs if p.name != args.name]
    if args.command == 'update' and args.ref and len(named) != 1:
        sys.exit('context-packs: --ref pins one pack, so name exactly one.')
    return packs


def check(packs, known):
    """Stop unless every pack, import packs included, has a name of its own and a folder no other holds."""
    names = [p.name for p in packs] + [i.pack.name for i in known if i.id]
    for name in sorted({n for n in names if names.count(n) > 1}):
        sys.exit(f'context-packs: more than one pack is named {name}, counting import packs. Commands name a pack '
                 'alone, so rename one.')
    # The folder inside would sync twice, maybe at another ref. Origins compare as written, so the same repo spelled
    # two ways gets past this.
    for a, b in itertools.combinations(packs + [i.pack for i in known], 2):
        outer, inner = sorted((PurePosixPath(a.path).parts, PurePosixPath(b.path).parts), key=len)
        if a.origin == b.origin and inner[:len(outer)] == outer:
            sys.exit(f'context-packs: the {a.name} and {b.name} packs overlap: one\'s folder in {a.origin} holds the '
                     'other\'s, so its rules would sync twice. Keep only one of them.')


def show(packs, known):
    """Each pack: its folder, or for one from an import pack, where it comes from and its pin, with the import packs
    it holds under it."""
    def line(pack):
        return f'{pack.name}  {pack.origin}' + f'  {pack.path}' * bool(pack.path) + f' @ {pack.ref}' * bool(pack.ref)
    pins = {i.holder: i.pack for i in known if not i.id}
    for pack in packs:
        print(line(pins[pack.name]) if pack.name in pins else f'{pack.name}  {pack.path}')
        for imported in known:
            if imported.holder == pack.name and imported.id:
                print(f'  {line(imported.pack)}')


def main():
    parser = argparse.ArgumentParser(prog='context-packs', description=__doc__)
    parser.add_argument('--dir', type=Path, default=Path.cwd(),
                        help='the folder to sync, if not the current one')
    commands = parser.add_subparsers(dest='command', metavar='command',
                                     description='leave out the command to resync every pack at its pinned ref')
    add = commands.add_parser('add', help='install a pack: one from git as an import pack pinned to its origin\'s '
                                          'latest commit or to --ref, or a folder on disk where it is')
    add.add_argument('name', help='what to call the pack in AGENTS.md and docs/agents/packs/')
    add.add_argument('origin', help='a git URL, or the path of a folder on disk, such as docs/agents/project or '
                                    '../agent-config')
    add.add_argument('--path', default='', help='the folder in the origin holding the pack, if not its root')
    add.add_argument('--ref', help='a tag or commit to pin a pack from git to')
    add.add_argument('--into', help=f'the folder to write a pack from git\'s import pack into, as <folder>/<name>/; '
                                    f'{imports.INTO} if left out. Inside a pack of yours, the pack syncs in that '
                                    'pack\'s block')
    add.add_argument('--when', help="a pack from git's when, in place of its author's: a row, or always to paste it in")
    remove = commands.add_parser('remove', help='uninstall a pack')
    remove.add_argument('name')
    update = commands.add_parser('update', help='move pinned packs on: one pinned to a commit to the tip of its '
                                                "origin's default branch, one pinned to a release tag to the newest "
                                                'release in its series')
    update.add_argument('names', nargs='*', help='the packs to update; all of them if left out')
    update.add_argument('--ref', help='a tag or commit to pin the one named pack to instead')
    commands.add_parser('list', help='list the packs, where each comes from, and its pin')
    args = parser.parse_args()
    repo = args.dir
    if not repo.is_dir():
        sys.exit(f'context-packs: {repo} is not a folder')

    file = instructions(repo)
    found = region(repo, file)
    before = imports.find(repo, found.packs)
    packs = apply(args, found, [i.pack.name for i in before if i.id])
    packs, known, edits = imports.apply(args, repo, packs, before)
    check(packs, known)

    with contextlib.ExitStack() as stack:
        imported = imports.trees(repo, packs, known, stack)
        # Each marker's pack as it renders, from the pack its import pack names if it names one.
        rendered = {}
        for pack in packs:
            named = imported[pack.name].pop('', None)
            if named:
                rendered[pack.name] = (named.pack, named.root, named.source)
            else:
                source = fetch(repo, pack, stack)
                rendered[pack.name] = (pack, tree.load(source, pack, imported=imported[pack.name]), source)
        if args.command == 'list':
            show(packs, known)
            return

        for gone in {p.name for p in found.packs} - {p.name for p in packs}:
            if (repo / PACKS / gone).exists():
                shutil.rmtree(repo / PACKS / gone)
        blocks = {HEADER: block(HEADER_START, HEADER_RULES)}
        for pack in packs:
            content, root, source = rendered[pack.name]
            generated = repo / PACKS / pack.name
            if generated.exists():
                shutil.rmtree(generated)
            tree.write(root, content, source, repo)
            blocks[pack.name] = block(pack.start(), tree.body(root, content), snapshot(generated))
        if (repo / PACKS).is_dir() and not any((repo / PACKS).iterdir()):
            (repo / PACKS).rmdir()
        for pack_md, text in edits:
            if text is None:
                shutil.rmtree(repo / pack_md.parent)
            else:
                (repo / pack_md).parent.mkdir(parents=True, exist_ok=True)
                (repo / pack_md).write_text(text, encoding='utf-8')
        text = found.text[:found.start] + '\n'.join(blocks.values()) + found.text[found.end:]
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
