"""A pack's content as a tree of packs: the installed pack's pack.md and docs, and each folder holding a pack.md of
its own nested inside it. A folder without a pack.md only groups files, whose docs join the nearest pack's table."""
from pathlib import Path
import re
import shutil
import sys
from typing import NamedTuple, Tuple

from packs import Pack

FRONT = re.compile(r'---\n(.*?)\n---\n', re.DOTALL)


class Doc(NamedTuple):
    path: str
    when: str


class Node(NamedTuple):
    """A pack in the tree. Its id is its folder relative to the installed pack's, '' for the installed pack itself,
    and paths are relative to that folder too. Its files are every one it brings, docs included, but not those of
    the packs nested in it."""
    id: str
    fields: dict
    rules: str
    docs: Tuple[Doc, ...]
    files: Tuple[str, ...]
    children: Tuple['Node', ...]
    imports: Tuple['Imported', ...] = ()

    @property
    def row(self):
        """Whether the pack gets a row pointing at its index, rather than having its rules and table pasted into its
        block, or after the rules and table of the pack holding it: it does when it has a when other than always.
        A pack renders the same installed on its own as inside another."""
        return self.fields.get('when', 'always') != 'always'

    def nested(self):
        """Every pack nested in this one, at any depth, parents before their children."""
        for child in self.children:
            yield child
            yield from child.nested()


class Imported(NamedTuple):
    """The pack an import pack names, at the import pack's id in the pack holding it: its root carries the import
    pack's fields and rules in place of its own, and source is the folder holding its content."""
    id: str
    pack: Pack
    root: Node
    source: Path


def imports_a_pack(text):
    """Whether a pack.md's front matter names a pack to import."""
    match = FRONT.match(text)
    return bool(match) and any(line.startswith('from: ') for line in match.group(1).split('\n'))


def front(text, where, keys):
    """text's front matter as fields, keeping only those named in keys, and the text after it."""
    match = FRONT.match(text)
    pairs = [line.split(': ', 1) for line in match.group(1).split('\n')] if match else []
    fields = dict(p for p in pairs if len(p) == 2)
    if len(fields) != len(pairs):
        sys.exit(f'context-packs: {where} has front matter that isn\'t `key: value` lines.')
    unknown = sorted(set(fields) - set(keys))
    if unknown:
        sys.exit(f'context-packs: {where} has front matter context-packs doesn\'t know: {", ".join(unknown)}. '
                 f'It takes only {", ".join(f"`{k}`" for k in keys)}. Remove it, or update context-packs if the '
                 'pack needs a newer version.')
    return fields, text[match.end():] if match else text


def load(folder, pack, id='', imported=None):
    """The pack in folder/id and the packs nested in it, with folder holding the pack fetched from pack. imported
    holds the packs its import packs name, by their ids, for a pack that can hold import packs, and is None for any
    other."""
    def where(path):
        return f'{(Path(pack.path) / path).as_posix()} in {pack.origin}'

    home = Path(id)
    pack_md = folder / home / 'pack.md'
    fields, rules = front(pack_md.read_text(encoding='utf-8'), where(home / 'pack.md'),
                          ('when',)) if pack_md.is_file() else ({}, '')
    # A nested pack's when is its row in its parent's table. The installed pack needs none: without one, it's pasted
    # in.
    if id and 'when' not in fields:
        sys.exit(f'context-packs: {where(home / "pack.md")} must start with front matter saying when to read it, '
                 'since it\'s nested in another pack:\n\n---\nwhen: Editing `web/**`\n---')
    # The end marker has to start its own line, or the next sync can't find the block.
    if rules and not rules.endswith('\n'):
        rules += '\n'
    docs, files, children = [], [], []

    def walk(rel):
        for entry in sorted((folder / rel).iterdir()):
            path = rel / entry.name
            if entry.name.startswith('.') or path == home / 'pack.md':
                continue
            if entry.is_dir() and (entry / 'pack.md').is_file():
                # A pack that can hold import packs has them passed in, as the command leaves them, so the ones on
                # disk are skipped.
                if imports_a_pack((entry / 'pack.md').read_text(encoding='utf-8')):
                    if imported is None:
                        sys.exit(f'context-packs: {where(path / "pack.md")} imports a pack, but only a pack read from '
                                 'a folder on disk, installed in AGENTS.md, can hold import packs.')
                    continue
                twin = path.parent / f'{entry.name}.md'
                if (folder / twin).is_file():
                    sys.exit(f'context-packs: {where(path)} holds a pack.md and sits beside {where(twin)}, so its '
                             f'index and that doc would both be {twin.as_posix()}. Rename one.')
                children.append(load(folder, pack, path.as_posix(), imported))
            elif entry.is_dir():
                walk(path)
            else:
                files.append(path.as_posix())
                if entry.suffix == '.md':
                    doc_fields, _ = front(entry.read_text(encoding='utf-8'), where(path), ('when',))
                    if 'when' not in doc_fields:
                        sys.exit(f'context-packs: {where(path)} must start with front matter saying when to read '
                                 'it:\n\n---\nwhen: Editing `**/*.ts`\n---')
                    docs.append(Doc(path.as_posix(), doc_fields['when']))

    walk(home)
    node = Node(id, fields, rules, tuple(docs), tuple(files), tuple(children))
    return attach(node, imported) if imported and not id else node


def attach(node, imported):
    """node with each of the imported packs, by id, given to the deepest pack whose folder holds its import pack."""
    children, rest = [], dict(imported)
    for child in node.children:
        under = {i: rest.pop(i) for i in sorted(rest) if i.startswith(f'{child.id}/')}
        children.append(attach(child, under))
    return node._replace(children=tuple(children), imports=tuple(rest[i] for i in sorted(rest)))


def index(node, pack):
    """Where a pack's generated index sits: pack.md for the installed pack, since no doc can have that name."""
    return pack.generated / f'{node.id or "pack"}.md'


def table(title, rows):
    """A table of (when, path) rows under its heading, or nothing without rows."""
    return (f'## {title} context\n\n| When | Read |\n|---|---|\n'
            + ''.join(f'| {when} | `{path.as_posix()}` |\n' for when, path in rows)) if rows else ''


def render(node, pack):
    """The node's rules, then its table: a row for each of its docs, and for each pack nested in it or imported
    into it that gets one. Each of those packs that doesn't is rendered the same way after it."""
    rows = sorted([(d.path[:-len('.md')], d.when, pack.synced / d.path) for d in node.docs]
                  + [(c.id, c.fields['when'], index(c, pack)) for c in node.children if c.row]
                  + [(i.id, i.root.fields['when'], index(i.root, i.pack)) for i in node.imports if i.root.row])
    title = f'{pack.name}/{node.id}' if node.id else pack.name
    pasted = ([render(c, pack) for c in node.children if not c.row]
              + [render(i.root, i.pack) for i in node.imports if not i.root.row])
    return '\n'.join(part for part in (node.rules, table(title, [r[1:] for r in rows]), *pasted) if part)


def body(root, pack):
    """The installed pack's block: a row pointing at its index if it gets one, else its rules and table."""
    return table(pack.name, [(root.fields['when'], index(root, pack))]) if root.row else render(root, pack)


def write(root, pack, source, repo):
    """Copy the packs' files from source into repo, unless the pack is in repo already, and write the index of each
    pack that gets a row."""
    for node in [root, *root.nested()]:
        copies = [] if pack.local else [(source / path, repo / pack.synced / path) for path in node.files]
        for origin, target in copies:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(origin, target)
        if node.row:
            target = repo / index(node, pack)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(render(node, pack), encoding='utf-8')
        for imported in node.imports:
            write(imported.root, imported.pack, imported.source, repo)
