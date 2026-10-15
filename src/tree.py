"""The packs in context-packs/ as a tree: the repo's own pack.md and docs, each folder holding a pack.md of its own
nested inside, and each import pack replaced by the pack it names. A folder without a pack.md only groups files,
whose docs join the nearest pack's table."""
from pathlib import Path
import re
import shutil
import sys
from typing import NamedTuple, Tuple

from packs import REPO, Pack, fetch, folder, local, overlap, place

FRONT = re.compile(r'---\n(.*?)\n---\n', re.DOTALL)
# An import pack's front matter: its when, which replaces the imported pack's, and where that pack comes from.
IMPORT_KEYS = ('when', 'from', 'path', 'ref')


class Doc(NamedTuple):
    path: str
    when: str


class Node(NamedTuple):
    """A pack in the tree. Its id is its folder relative to the folder its content was read from, '' for the pack at
    the top, and paths are relative to that folder too. Its files are every one it brings, docs included, but not
    those of the packs nested in it."""
    id: str
    fields: dict
    rules: str
    docs: Tuple[Doc, ...]
    files: Tuple[str, ...]
    children: Tuple['Node', ...]
    imports: Tuple['Imported', ...]

    @property
    def row(self):
        """Whether the pack gets a row pointing at its index, rather than having its rules and table inlined after
        the rules and table of the pack holding it: it does when it has a when other than always."""
        return self.fields.get('when', 'always') != 'always'

    def nested(self):
        """Every pack nested in this one, at any depth, parents before their children."""
        for child in self.children:
            yield child
            yield from child.nested()


class Imported(NamedTuple):
    """The pack an import pack names, at the import pack's folder in the pack holding it: its root carries the import
    pack's when and rules ahead of its own, and source is the folder holding its content."""
    id: str
    pack: Pack
    root: Node
    source: Path


def imports_a_pack(text):
    """Whether a pack.md's front matter names a pack to import: another repo's, or a folder of its own repo's."""
    match = FRONT.match(text)
    return bool(match) and any(line.startswith(('from: ', 'path: ')) for line in match.group(1).split('\n'))


def front(text, where, keys):
    """text's front matter as fields, keeping only those named in keys, and the text after it."""
    match = FRONT.match(text)
    pairs = [line.split(': ', 1) for line in match.group(1).split('\n')] if match else []
    fields = dict(p for p in pairs if len(p) == 2)
    if len(fields) != len(pairs):
        sys.exit(f'context-packs: {where} has front matter that isn\'t `key: value` lines.')
    if fields and not keys:
        sys.exit(f'context-packs: {where} takes no front matter, since its rules are always inlined. '
                 f'Remove {", ".join(sorted(fields))}.')
    unknown = sorted(set(fields) - set(keys))
    if unknown:
        sys.exit(f'context-packs: {where} has front matter context-packs doesn\'t know: {", ".join(unknown)}. '
                 f'It takes only {", ".join(f"`{k}`" for k in keys)}. Remove it, or update context-packs if the '
                 'pack needs a newer version.')
    return fields, text[match.end():] if match else text


def read(file):
    return file.read_text(encoding='utf-8')


def load(repo, stack):
    """The tree of context-packs/ in repo, with each pack it imports fetched into a folder stack cleans up. Stops
    when two packs overlap, which also catches a pack importing a folder that holds it. A folder imported in two
    places, such as one two packs from the same repo both include, renders in each, at each one's ref."""
    # Every pack loaded so far, and the ones being loaded: the pack claiming a folder and those holding it.
    claimed, loading = [], []

    def claim(pack):
        here = place(repo, pack)
        for other, there in claimed:
            shared = here == there and other not in loading
            if overlap(here, there) and not shared:
                sys.exit(f'context-packs: the {other.id or "context-packs"} and {pack.id} packs overlap: one\'s '
                         'folder holds the other\'s, so its rules would sync twice. Keep only one of them.')
        claimed.append((pack, here))

    def imported(holder, source, rel):
        """The pack the import pack at rel in holder names, holder's source holding holder's content."""
        where = holder.where(rel / 'pack.md')
        others = sorted(p.name for p in (source / rel).iterdir() if p.name != 'pack.md' and not p.name.startswith('.'))
        if others:
            sys.exit(f'context-packs: {holder.where(rel)} is an import pack, so it holds only its pack.md. Move '
                     f'{", ".join(others)} beside it.')
        fields, rules = front(read(source / rel / 'pack.md'), where, IMPORT_KEYS)
        id = '/'.join(part for part in (holder.id, rel.as_posix()) if part)
        # from names another repo, and without it the path is a folder of the repo the import pack is in: the
        # synced repo for context-packs/, or the repo of the pack from elsewhere holding it.
        origin, path = fields.get('from'), folder('.', fields.get('path', ''))
        if path == '..' or path.startswith(('../', '/')):
            sys.exit(f'context-packs: {where} imports {path}, which is outside the repo '
                     f'{"its from names" if origin else "it is in"}. Name the other repo in `from`, and the folder in '
                     'it in `path`.')
        path = '' if path == '.' else path
        if origin and not holder.local:
            sys.exit(f'context-packs: {where} imports {origin}, but it sits in a pack from git, which can import only '
                     'folders of its own repo, with `path` alone.')
        if (not origin or local(origin)) and 'ref' in fields:
            sys.exit(f'context-packs: {where} pins a folder on disk to a ref, but a folder on disk is read from its '
                     'working tree, and a folder of the pack\'s own repo moves with that pack. Remove the ref line, '
                     'or import the pack by its git URL to pin it.')
        if not origin:
            pack = Pack(id, holder.origin, path, holder.ref)
        elif local(origin):
            pack = Pack(id, folder(holder.origin, origin), path, None)
        else:
            if 'ref' not in fields:
                sys.exit(f'context-packs: {where} imports {origin} without a ref to pin it to. Add `ref: <tag or '
                         'commit>`, or delete the folder and add the pack again.')
            pack = Pack(id, origin, path, fields['ref'])
        claim(pack)
        content = fetch(repo, pack, stack)
        loading.append(pack)
        root = tree(pack, content, '', ('when',))
        loading.pop()
        if rules and not rules.endswith('\n'):
            rules += '\n'
        root = root._replace(fields={**root.fields, **{k: v for k, v in fields.items() if k == 'when'}},
                             rules='\n'.join(r for r in (rules, root.rules) if r))
        return Imported(rel.as_posix(), pack, root, content)

    def tree(pack, source, id, keys):
        """The pack at the folder id in source, which holds pack's content, and the packs nested in it."""
        home = Path(id)
        pack_md = source / home / 'pack.md'
        fields, rules = front(read(pack_md), pack.where(home / 'pack.md'), keys) if pack_md.is_file() else ({}, '')
        # A nested pack's when is its row in its parent's table. The pack at the top needs none: without one, it's
        # inlined.
        if id and 'when' not in fields:
            sys.exit(f'context-packs: {pack.where(home / "pack.md")} must start with front matter saying when to '
                     'read it, since it\'s nested in another pack:\n\n---\nwhen: Editing `web/**`\n---')
        # The end marker has to start its own line, or the next sync can't find the block.
        if rules and not rules.endswith('\n'):
            rules += '\n'
        docs, files, children, imports = [], [], [], []

        def walk(rel):
            for entry in sorted((source / rel).iterdir()):
                path = rel / entry.name
                if entry.name.startswith('.') or path == home / 'pack.md' or (not pack.id and path == Path('gen')):
                    continue
                if entry.is_dir() and (entry / 'pack.md').is_file():
                    if imports_a_pack(read(entry / 'pack.md')):
                        imports.append(imported(pack, source, path))
                        continue
                    twin = path.parent / f'{entry.name}.md'
                    if (source / twin).is_file():
                        sys.exit(f'context-packs: {pack.where(path)} holds a pack.md and sits beside '
                                 f'{pack.where(twin)}, so its index and that doc would both be {twin.as_posix()}. '
                                 'Rename one.')
                    children.append(tree(pack, source, path.as_posix(), ('when',)))
                elif entry.is_dir():
                    walk(path)
                else:
                    files.append(path.as_posix())
                    if entry.suffix == '.md':
                        docs.append(Doc(path.as_posix(), when(pack, path, read(entry))))

        if (source / home).is_dir():
            walk(home)
        return Node(id, fields, rules, tuple(docs), tuple(files), tuple(children), tuple(imports))

    claim(REPO)
    loading.append(REPO)
    return tree(REPO, repo / REPO.synced, '', ())


def when(pack, path, text):
    """The when of the doc at path in pack, whose text is text."""
    fields, _ = front(text, pack.where(path), ('when',))
    if 'when' not in fields:
        sys.exit(f'context-packs: {pack.where(path)} must start with front matter saying when to read it:\n\n'
                 '---\nwhen: Editing `**/*.ts`\n---')
    if fields['when'] == 'always':
        sys.exit(f'context-packs: {pack.where(path)} has `when: always`, but only a pack.md is inlined. Move its '
                 'rules into the pack.md of the pack holding it, or give it a when saying when to read it.')
    return fields['when']


def index(node, pack):
    """Where a pack's generated index sits: pack.md for the pack at the top, since no doc can have that name."""
    return pack.generated / f'{node.id or "pack"}.md'


def table(heading, rows):
    """A table of (when, path) rows under its heading, or nothing without rows."""
    return (f'{heading}\n\n| When | Read |\n|---|---|\n'
            + ''.join(f'| {when} | `{path.as_posix()}` |\n' for when, path in rows)) if rows else ''


def name(node, pack):
    """The pack's folder under context-packs/, '' for context-packs/ itself."""
    return '/'.join(part for part in (pack.id, node.id) if part)


def heading(node, pack):
    return f'## {name(node, pack)} context' if name(node, pack) else '## Context'


def inline(node, pack):
    """The pack rendered where its parent's rules and table end, between markers naming it, which only show people
    reading the file where each pack starts and ends."""
    return (f'<!-- context-packs:pack {name(node, pack)} -->\n{render(node, pack)}'
            f'<!-- context-packs:pack-end {name(node, pack)} -->\n')


def render(node, pack):
    """The node's rules, then its table: a row for each of its docs, and for each pack nested in it or imported
    into it that gets one. Each of those packs that doesn't is rendered the same way after it."""
    rows = sorted([(d.path[:-len('.md')], d.when, pack.synced / d.path) for d in node.docs]
                  + [(c.id, c.fields['when'], index(c, pack)) for c in node.children if c.row]
                  + [(i.id, i.root.fields['when'], index(i.root, i.pack)) for i in node.imports if i.root.row])
    inlined = ([inline(c, pack) for c in node.children if not c.row]
               + [inline(i.root, i.pack) for i in node.imports if not i.root.row])
    return '\n'.join(part for part in (node.rules, table(heading(node, pack), [r[1:] for r in rows]), *inlined)
                     if part)


def write(root, pack, source, repo):
    """Copy the packs' files from source into repo, unless the pack is local, and write the index of each pack that
    gets a row, then do the same for each pack imported into them."""
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
