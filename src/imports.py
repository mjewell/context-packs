"""The import packs in context-packs/: folders whose pack.md names a pack from elsewhere, which syncs in their place.
The commands add, remove and move the pins of these; the ones that packs from elsewhere hold are theirs to change."""
import contextlib
import os
from pathlib import Path
import re
import shutil
import sys
from typing import NamedTuple, Optional

import origins
from packs import ROOT, local
import tree

REF = re.compile(r'^ref: .*$', re.MULTILINE)
# A folder under context-packs/: names of letters, digits, dots, dashes and underscores, none starting with a dot.
ID = re.compile(r'[A-Za-z0-9_-][A-Za-z0-9._-]*(?:/[A-Za-z0-9_-][A-Za-z0-9._-]*)*')


class Import(NamedTuple):
    """An import pack in context-packs/: its folder there, its pack.md relative to the synced repo and that file's
    text, and where the pack it names comes from."""
    id: str
    file: str
    text: str
    origin: str
    path: str
    ref: Optional[str]


def scan(repo):
    """The import packs in context-packs/, by the order of their folders."""
    root = repo / ROOT
    if not root.is_dir():
        return []
    found = []
    for pack_md in sorted(root.rglob('pack.md')):
        rel = pack_md.relative_to(root)
        # context-packs/pack.md is the repo's own rules, never an import pack.
        if len(rel.parts) == 1 or rel.parts[0] == 'gen' or any(p.startswith('.') for p in rel.parts):
            continue
        text = tree.read(pack_md)
        if tree.imports_a_pack(text):
            fields, _ = tree.front(text, (ROOT / rel).as_posix(), tree.IMPORT_KEYS)
            found.append(Import(rel.parent.as_posix(), (ROOT / rel).as_posix(), text, fields.get('from', '.'),
                                fields.get('path', ''), fields.get('ref')))
    return found


def command(args, repo, imports):
    """The files the command writes, as (pack.md, text) pairs relative to repo, with None for text deleting the
    import pack's folder, given the import packs there before it runs."""
    ids = [i.id for i in imports]
    if args.command == 'add':
        if not ID.fullmatch(args.id) or args.id.split('/')[0] == 'gen':
            sys.exit(f'context-packs: {args.id} can\'t name a pack. Use a folder under {ROOT.as_posix()}/, other than '
                     'gen/, named with letters, digits, dots, dashes and underscores, not starting with a dot.')
        target = ROOT / args.id
        if (repo / target).exists():
            sys.exit(f'context-packs: {target.as_posix()} already exists. Choose another id, or remove it.')
        if local(args.origin) and args.ref:
            sys.exit(f'context-packs: {args.origin} is a folder on disk, which syncs from its working tree, so '
                     'it takes no --ref.')
        origin, path, ref = args.origin, args.path, None
        if local(origin):
            inside = os.path.relpath(os.path.join(os.path.abspath(repo), origin, path), os.path.abspath(repo))
            # A folder of the synced repo is named by its path alone, so it reads the same however add was given it.
            if inside != '..' and not inside.startswith('..' + os.sep):
                origin, path = None, Path(inside).as_posix()
        else:
            ref = origins.pin(origin, args.ref) if args.ref else origins.tip(origin)
        text = ('---\n' + f'when: {args.when}\n' * bool(args.when) + f'from: {origin}\n' * bool(origin)
                + f'path: {path}\n' * bool(path) + f'ref: {ref}\n' * bool(ref) + '---\n')
        return [((target / 'pack.md').as_posix(), text)]
    named = [args.id] if args.command == 'remove' else getattr(args, 'ids', [])
    unknown = [n for n in named if n not in ids]
    if unknown:
        sys.exit(f'context-packs: {args.dir} has no import pack {", ".join(unknown)} in {ROOT.as_posix()}/. '
                 f'Its import packs: {", ".join(ids) or "none"}.')
    if args.command == 'remove':
        return [(i.file, None) for i in imports if i.id == args.id]
    if args.command != 'update':
        return []
    if args.ref and len(named) != 1:
        sys.exit('context-packs: --ref pins one pack, so name exactly one.')
    edits = []
    for imported in imports:
        if named and imported.id not in named:
            continue
        if local(imported.origin):
            if args.ref:
                sys.exit(f'context-packs: the {imported.id} pack syncs from the working tree of {imported.origin}, '
                         'so it takes no --ref.')
            continue
        ref = origins.pin(imported.origin, args.ref) if args.ref else origins.latest(imported.origin, imported.ref)
        if ref != imported.ref:
            edits.append((imported.file, REF.sub(f'ref: {ref}', imported.text, count=1)))
    return edits


@contextlib.contextmanager
def applied(repo, edits):
    """Write the edits, and put everything back if the sync stops before it's done."""
    undo = []
    try:
        for file, text in edits:
            pack_md = repo / file
            if text is None:
                old = tree.read(pack_md)
                shutil.rmtree(pack_md.parent)
                undo.append(lambda pack_md=pack_md, old=old: (pack_md.parent.mkdir(parents=True),
                                                              pack_md.write_text(old, encoding='utf-8')))
                continue
            created = next((p for p in reversed(pack_md.parents) if not p.exists()), None)
            if created:
                pack_md.parent.mkdir(parents=True)
                undo.append(lambda created=created: shutil.rmtree(created))
            else:
                old = tree.read(pack_md)
                undo.append(lambda pack_md=pack_md, old=old: pack_md.write_text(old, encoding='utf-8'))
            pack_md.write_text(text, encoding='utf-8')
        yield
    except BaseException:
        for step in reversed(undo):
            step()
        raise
