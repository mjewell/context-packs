#!/usr/bin/env python3
"""Sync context packs into a repository, or any folder such as the one above the repositories: the packs in
context-packs/, the repo's own and those its import packs name, as one block in AGENTS.md, with the docs of packs from
git and the indexes of nested packs in context-packs/gen/."""
import argparse
import contextlib
import os
from pathlib import Path
import shutil
import sys

import imports
import report
from blocks import HEADER, block, instructions, region, snapshot
from packs import GEN, REPO
import tree


def show(found):
    """Each import pack: its id, where its pack comes from, and its pin."""
    for i in found:
        print(f'{i.id}  {i.origin}' + f'  {i.path}' * bool(i.path) + f' @ {i.ref}' * bool(i.ref))


def main():
    parser = argparse.ArgumentParser(prog='context-packs', description=__doc__)
    parser.add_argument('--dir', type=Path, default=Path.cwd(),
                        help='the folder to sync, if not the current one')
    commands = parser.add_subparsers(dest='command', metavar='command',
                                     description='leave out the command to resync every pack at its pinned ref')
    add = commands.add_parser('add', help='install a pack as an import pack in context-packs/<id>/: one from git '
                                          'pinned to its origin\'s latest commit or to --ref, or a folder on disk '
                                          'read where it is')
    add.add_argument('id', help='the folder under context-packs/ to put the import pack in, such as core or '
                                'project/typescript')
    add.add_argument('origin', help='a git URL, or the path of a folder on disk, such as docs/agents or '
                                    '../agent-config')
    add.add_argument('--path', default='', help='the folder in the origin holding the pack, if not its root')
    add.add_argument('--ref', help='a tag or commit to pin a pack from git to')
    add.add_argument('--when', help="the pack's when, in place of its author's: a row, or always to inline it")
    remove = commands.add_parser('remove', help='uninstall a pack, deleting its import pack')
    remove.add_argument('id')
    update = commands.add_parser('update', help='move pinned packs on: one pinned to a commit to the tip of its '
                                                "origin's default branch, one pinned to a release tag to the newest "
                                                'release in its series')
    update.add_argument('ids', nargs='*', help='the packs to update; all of them if left out')
    update.add_argument('--ref', help='a tag or commit to pin the one named pack to instead')
    commands.add_parser('list', help='list the import packs, where each comes from, and its pin')
    args = parser.parse_args()
    repo = args.dir
    if not repo.is_dir():
        sys.exit(f'context-packs: {repo} is not a folder')

    file = instructions(repo)
    found = region(repo, file)
    before = imports.scan(repo)
    if args.command == 'list':
        show(before)
        return
    edits = imports.command(args, repo, before)

    with imports.applied(repo, edits), contextlib.ExitStack() as stack:
        root = tree.load(repo, stack)
        if (repo / GEN).exists():
            shutil.rmtree(repo / GEN)
        tree.write(root, REPO, repo / REPO.synced, repo)
        rendered = tree.render(root, REPO)
        written = block(HEADER + '\n' * bool(rendered) + rendered, snapshot(repo / GEN))
        text = found.text[:found.start] + written + found.text[found.end:]
        created = not file.exists()
        file.write_bytes(text.encode('utf-8'))
    # A new AGENTS.md gets CLAUDE.md linked to it, so Claude Code reads it too. A repo that already has its own
    # instruction files keeps them as they are.
    linked = created and not os.path.lexists(repo / 'CLAUDE.md')
    if linked:
        (repo / 'CLAUDE.md').symlink_to('AGENTS.md')
    for line in report.changes(found, written, created, linked, before, imports.scan(repo)):
        print(line)


if __name__ == '__main__':
    main()
