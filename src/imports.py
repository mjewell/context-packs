"""Import packs: folders whose pack.md names a pack from elsewhere, which syncs in their place with the import pack's
when and rules in place of its own, so the repo decides how that pack loads. A marker can name one, which then gets a
block, or one can sit in a pack read from a folder on disk, which then holds it."""
import os
from pathlib import Path
import re
import sys
from typing import NamedTuple

import origins
from packs import PACKS, Pack, fetch, folder, local
import tree

KEYS = ('when', 'from', 'path', 'ref')
REF = re.compile(r'^ref: .*$', re.MULTILINE)
INTO = 'docs/agents'


class Import(NamedTuple):
    """An import pack: its pack.md, relative to the synced repo, and that file's text; the name of the pack whose
    marker names it or holds it, and its id there, '' for the one a marker names; and the pack it names, whose files
    go under that pack's generated folder."""
    file: Path
    text: str
    holder: str
    id: str
    pack: Pack

    def front(self):
        """The fields and rules that replace the imported pack's root's."""
        fields, rules = tree.front(self.text, self.file.as_posix(), KEYS)
        if rules and not rules.endswith('\n'):
            rules += '\n'
        return {k: v for k, v in fields.items() if k == 'when'}, rules


def parse(holder, file, text):
    """The import pack at file, which holder's marker names or which sits in holder's folder, from its text."""
    where = file.as_posix()
    fields, _ = tree.front(text, where, KEYS)
    origin = fields['from']
    if local(origin) and 'ref' in fields:
        sys.exit(f'context-packs: {where} pins {origin} to a ref, but a path is a folder on disk, read from its '
                 'working tree. Remove the ref line, or import the pack by its git URL to pin it.')
    if not local(origin) and 'ref' not in fields:
        sys.exit(f'context-packs: {where} imports {origin} without a ref to pin it to. Add `ref: <tag or commit>`, '
                 'or delete the folder and add the pack again.')
    named = file.parent == Path(holder.path)
    id = '' if named else file.parent.relative_to(holder.path).as_posix()
    home = PACKS / holder.name if named else holder.generated / id
    return Import(file, text, holder.name, id,
                  Pack(holder.name if named else file.parent.name, origin, fields.get('path', ''), fields.get('ref'),
                       home))


def only_pack_md(repo, file):
    others = sorted(p.name for p in (repo / file.parent).iterdir() if p.name != 'pack.md' and not p.name.startswith('.'))
    if others:
        sys.exit(f'context-packs: {file.parent.as_posix()} is an import pack, so it holds only its pack.md. Move '
                 f'{", ".join(others)} beside it.')


def find(repo, packs):
    """The import packs the markers name, and those in the packs they name that are read from a folder on disk."""
    found = []
    for holder in packs:
        home = Path(holder.path)
        named = repo / home / 'pack.md'
        if named.is_file() and tree.imports_a_pack(named.read_text(encoding='utf-8')):
            only_pack_md(repo, home / 'pack.md')
            found.append(parse(holder, home / 'pack.md', named.read_text(encoding='utf-8')))
            continue
        for pack_md in sorted((repo / home).rglob('pack.md')):
            rel = pack_md.relative_to(repo / home)
            if rel == Path('pack.md') or any(part.startswith('.') for part in rel.parts):
                continue
            text = pack_md.read_text(encoding='utf-8')
            if tree.imports_a_pack(text):
                only_pack_md(repo, home / rel)
                found.append(parse(holder, home / rel, text))
    return found


def trees(repo, packs, known, stack):
    """For each marker, the packs its import packs name, loaded with the import packs' fields and rules in place of
    their roots', by id, with '' for the import pack the marker names."""
    imported = {p.name: {} for p in packs}
    for i in known:
        source = fetch(repo, i.pack, stack)
        fields, rules = i.front()
        root = tree.load(source, i.pack)
        root = root._replace(fields={**root.fields, **fields}, rules='\n'.join(r for r in (rules, root.rules) if r))
        imported[i.holder][i.id] = tree.Imported(i.id, i.pack, root, source)
    return imported


def within(path, outer):
    path, outer = Path(os.path.normpath(path)), Path(os.path.normpath(outer))
    return path == outer or outer in path.parents


def apply(args, repo, markers, packs, known):
    """The markers' packs and the import packs once the command has run, and the files to write for the import
    packs, as (pack.md, text) pairs, with None for text deleting the import pack's folder. markers names the packs
    the markers named before it ran."""
    packs, known, edits = list(packs), list(known), []
    named = {i.holder for i in known if not i.id}
    if args.command == 'add' and local(args.origin):
        for flag in ('into', 'when'):
            if getattr(args, flag):
                sys.exit(f'context-packs: {args.origin} is a folder on disk, which is added where it is and takes its '
                         f'when from its own pack.md, so it takes no --{flag}.')
        if args.ref:
            sys.exit(f'context-packs: {args.origin} is a folder on disk, which syncs from its working tree, so '
                     'it takes no --ref.')
        packs.append(Pack(args.name, '.', folder(args.origin, args.path), None))
        if not (repo / packs[-1].path).is_dir():
            sys.exit(f'context-packs: {packs[-1].path} isn\'t a folder, relative to {repo}.')
        known += find(repo, packs[-1:])
    if args.command == 'add' and not local(args.origin):
        into = args.into or INTO
        holder = next((p for p in packs if within(into, p.path)), None)
        if holder and holder.name in named:
            sys.exit(f'context-packs: {into} is inside the import pack {holder.path}, which holds only its pack.md.')
        file = Path(folder(into, args.name)) / 'pack.md'
        if (repo / file.parent).exists():
            sys.exit(f'context-packs: {file.parent.as_posix()} already exists. Choose another name, or remove it.')
        ref = origins.pin(args.origin, args.ref) if args.ref else origins.tip(args.origin)
        text = ('---\n' + f'when: {args.when}\n' * bool(args.when) + f'from: {args.origin}\n'
                + f'path: {args.path}\n' * bool(args.path) + f'ref: {ref}\n---\n')
        if not holder:
            holder = Pack(args.name, '.', file.parent.as_posix(), None)
            packs.append(holder)
        known.append(parse(holder, file, text))
        edits.append((file, text))
    if args.command == 'remove' and args.name in markers:
        # Only the import pack the marker names goes. Those its folder holds leave the sync with it, but their files
        # are the repo's, so they stay, as does one moved out of its folder that still has its name.
        edits += [(i.file, None) for i in known if i.holder == args.name and not i.id]
        known = [i for i in known if i.holder != args.name]
    elif args.command == 'remove':
        edits += [(i.file, None) for i in known if i.id and i.pack.name == args.name]
        known = [i for i in known if not (i.id and i.pack.name == args.name)]
    if args.command == 'update':
        for n, imported in enumerate(known):
            pack = imported.pack
            if args.names and pack.name not in args.names:
                continue
            if pack.local:
                if args.ref:
                    sys.exit(f'context-packs: the {pack.name} import pack syncs from the working tree of '
                             f'{pack.origin}, so it takes no --ref.')
                continue
            ref = origins.pin(pack.origin, args.ref) if args.ref else origins.latest(pack.origin, pack.ref)
            if ref != pack.ref:
                text = REF.sub(f'ref: {ref}', imported.text, count=1)
                known[n] = imported._replace(text=text, pack=pack._replace(ref=ref))
                edits.append((imported.file, text))
        for pack in packs:
            if args.ref and pack.name in args.names and pack.name not in named:
                sys.exit(f'context-packs: the {pack.name} pack syncs from the working tree of {pack.path}, so it '
                         'takes no --ref.')
    return packs, known, edits
