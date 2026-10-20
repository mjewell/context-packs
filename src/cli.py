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
import tempfile

import evals
import imports
import report
from blocks import HEADER, block, instructions, region, snapshot
from packs import GEN, REPO
import tree


def show(found):
    """Each import pack: its id, where its pack comes from, and its pin."""
    for i in found:
        print(f'{i.id}  {i.origin}' + f'  {i.path}' * bool(i.path) + f' @ {i.ref}' * bool(i.ref))


def generate(root, out, repo):
    """Write the generated files into out's context-packs/gen/, and return the block, whose hash covers them."""
    tree.write(root, REPO, repo / REPO.synced, out)
    rendered = tree.render(root, REPO)
    return block(HEADER + '\n' * bool(rendered) + rendered, snapshot(out / GEN))


def generated(out):
    """The files in out's context-packs/gen/, by their path in the synced repo."""
    folder = out / GEN
    return {(GEN / p.relative_to(folder)).as_posix(): p.read_bytes()
            for p in folder.rglob('*') if p.is_file()} if folder.is_dir() else {}


def check(file, found, written, out, repo):
    """Stop, naming what a sync would change, if the block or a generated file differs from what it would write into
    out. The block's hash covers the generated files, so any change to them changes the block too."""
    if not file.exists():
        sys.exit(f"context-packs: {file} doesn't exist, so the repo was never synced. Run `npx context-packs` and "
                 'commit the result.')
    if written == found.block:
        return
    fresh, current = generated(out), generated(repo)
    stale = sorted(path for path in {*fresh, *current} if fresh.get(path) != current.get(path))
    sys.exit(f'context-packs: {file}: the context-packs block is stale'
             + ', as are these generated files:\n\n' * bool(stale) + ''.join(f'  {path}\n' for path in stale)
             + '.\n' * (not stale) + '\nRun `npx context-packs` and commit the result.')


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
    update = commands.add_parser('update', help='move packs pinned to a commit to the tip of their origin\'s '
                                                'default branch, leaving those pinned to a tag')
    update.add_argument('ids', nargs='*', help='the packs to update; all of them if left out')
    update.add_argument('--ref', help='a tag or commit to pin the one named pack to instead')
    commands.add_parser('list', help='list the import packs, where each comes from, and its pin')
    commands.add_parser('check', help='exit 1 if a sync would change anything, writing nothing')
    evaluate = commands.add_parser('eval', help="run each doc's cases: prompts that should, or shouldn't, make an "
                                                'agent read it, each as a claude -p session in a copy of the repo')
    evaluate.add_argument('docs', nargs='*', help='the docs whose cases to run, as eval names them, such as '
                                                  'testing.md or core/testing.md; all of them if left out')
    evaluate.add_argument('--runs', type=int, default=1, help='how many times to run each prompt, 1 by default')
    evaluate.add_argument('--model', help='the model the sessions use, if not claude\'s default')
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
        if args.command in ('check', 'eval'):
            out = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix='context-packs-check-')))
            check(file, found, generate(root, out, repo), out, repo)
            # Cases run against the block as it is, so a stale one would test rows that are about to change.
            if args.command == 'eval':
                evals.run(root, repo, args)
            return
        if (repo / GEN).exists():
            shutil.rmtree(repo / GEN)
        written = generate(root, repo, repo)
        text = found.text[:found.start] + written + found.text[found.end:]
        created = not file.exists()
        file.write_bytes(text.encode('utf-8'))
    # A new AGENTS.md gets CLAUDE.md linked to it, so Claude Code reads it too. A repo that already has its own
    # instruction files keeps them as they are.
    linked = created and not os.path.lexists(repo / 'CLAUDE.md')
    if linked:
        (repo / 'CLAUDE.md').symlink_to('AGENTS.md')
    updating = [i.id for i in before if not args.ids or i.id in args.ids] if args.command == 'update' else []
    for line in report.changes(found, written, created, linked, before, imports.scan(repo), updating):
        print(line)


if __name__ == '__main__':
    main()
