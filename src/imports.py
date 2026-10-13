"""Import packs: folders in a pack read from disk whose pack.md names another pack, which syncs in their place with
the import pack's when and rules in place of its own, so the repo decides how that pack loads."""
import os
from pathlib import Path
import re
import sys
from typing import NamedTuple

import origins
from packs import Pack, local
import tree

KEYS = ('when', 'from', 'path', 'ref')
REF = re.compile(r'^ref: .*$', re.MULTILINE)


class Import(NamedTuple):
    """An import pack: its pack.md, relative to the synced repo, and that file's text; the name of the pack holding
    it, and its id there; and the pack it names, whose files go under the holder's generated folder."""
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
    """The import pack at file, inside holder's folder, from its pack.md's text."""
    where = file.as_posix()
    fields, _ = tree.front(text, where, KEYS)
    origin = fields['from']
    if local(origin) and 'ref' in fields:
        sys.exit(f'context-packs: {where} pins {origin} to a ref, but a path is a folder on disk, read from its '
                 'working tree. Remove the ref line, or import the pack by its git URL to pin it.')
    if not local(origin) and 'ref' not in fields:
        sys.exit(f'context-packs: {where} imports {origin} without a ref to pin it to. Add `ref: <tag or commit>`, '
                 'or delete the folder and import the pack again with add --into.')
    id = file.parent.relative_to(holder.synced).as_posix()
    return Import(file, text, holder.name, id,
                  Pack(file.parent.name, origin, fields.get('path', ''), fields.get('ref'), holder.generated / id))


def find(repo, packs):
    """The import packs in the packs read from disk, which each hold theirs as folders whose pack.md names a pack."""
    found = []
    for holder in (p for p in packs if p.local):
        folder = repo / holder.synced
        for pack_md in sorted(folder.rglob('pack.md')):
            rel = pack_md.relative_to(folder)
            if rel == Path('pack.md') or any(part.startswith('.') for part in rel.parts):
                continue
            text = pack_md.read_text(encoding='utf-8')
            if not tree.imports_a_pack(text):
                continue
            others = sorted(p.name for p in pack_md.parent.iterdir()
                            if p.name != 'pack.md' and not p.name.startswith('.'))
            if others:
                sys.exit(f'context-packs: {(holder.synced / rel.parent).as_posix()} is an import pack, so it holds only '
                         f'its pack.md. Move {", ".join(others)} beside it.')
            found.append(parse(holder, holder.synced / rel, text))
    return found


def within(folder, outer):
    folder, outer = Path(os.path.normpath(folder)), Path(os.path.normpath(outer))
    return folder == outer or outer in folder.parents


def apply(args, repo, packs, known):
    """The import packs once the command has run, and the files to write for them, as (pack.md, text) pairs, with
    None for text deleting the import pack's folder."""
    known, edits = list(known), []
    if args.command == 'add' and args.when and not args.into:
        sys.exit('context-packs: --when sets an import pack\'s when, so it goes with --into.')
    if args.command == 'add' and args.into:
        holder = next((p for p in packs if p.local and within(args.into, p.synced)), None)
        if not holder:
            sys.exit(f'context-packs: {args.into} isn\'t inside a pack read from a folder on disk, which holds import '
                     'packs. Install one first, such as with add project . --path docs/agents/project.')
        file = Path(os.path.normpath(args.into)) / args.name / 'pack.md'
        if (repo / file.parent).exists():
            sys.exit(f'context-packs: {file.parent.as_posix()} already exists. Choose another name, or remove it.')
        if local(args.origin) and args.ref:
            sys.exit(f'context-packs: {args.origin} is a folder on disk, which syncs from its working tree, so it '
                     'takes no --ref.')
        ref = None if local(args.origin) else origins.pin(args.origin, args.ref) if args.ref \
            else origins.tip(args.origin)
        text = ('---\n' + f'when: {args.when}\n' * bool(args.when) + f'from: {args.origin}\n'
                + f'path: {args.path}\n' * bool(args.path) + f'ref: {ref}\n' * bool(ref) + '---\n')
        imported = parse(holder, file, text)
        known.append(imported)
        edits.append((file, text))
    if args.command == 'remove':
        edits += [(i.file, None) for i in known if i.pack.name == args.name]
        known = [i for i in known if i.pack.name != args.name]
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
    return known, edits
