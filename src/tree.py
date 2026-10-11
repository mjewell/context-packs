"""A pack's content as a tree of packs: the installed pack's pack.md and docs, and each folder holding a pack.md of
its own nested inside it. A folder without a pack.md only groups files, whose docs join the nearest pack's table."""
from pathlib import Path
import re
import shutil
import sys
from typing import NamedTuple, Tuple

from packs import PACKS

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

    @property
    def optional(self):
        return 'optional' in self.fields

    @property
    def inline(self):
        return 'inline' in self.fields

    @property
    def row(self):
        """Whether the pack gets a row pointing at its index, rather than having its rules and table pasted into its
        parent's, or into the block for the installed pack. Its parent is wherever it's installed, so a pack renders
        the same installed on its own as inside another."""
        return 'when' in self.fields and not self.inline

    def nested(self):
        """Every pack nested in this one, at any depth, parents before their children."""
        for child in self.children:
            yield child
            yield from child.nested()


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
                 'A doc takes only `when`, and a pack.md takes `when`, `optional` and `inline`. Remove it, or update '
                 'context-packs if the pack needs a newer version.')
    return fields, text[match.end():] if match else text


def load(folder, pack, id=''):
    """The pack in folder/id and the packs nested in it, with folder holding the pack fetched from pack."""
    def where(path):
        return f'{(Path(pack.path) / path).as_posix()} in {pack.origin}'

    home = Path(id)
    if not id and (folder / 'agents.md').is_file():
        sys.exit(f'context-packs: {where("agents.md")} holds rules under the name packs used before 0.2.0. Rename it '
                 'to pack.md in the pack, or run update to move to a version of the pack that has one.')
    pack_md = folder / home / 'pack.md'
    fields, rules = front(pack_md.read_text(encoding='utf-8'), where(home / 'pack.md'),
                          ('when', 'optional', 'inline')) if pack_md.is_file() else ({}, '')
    for key, without in (('optional', 'installed whenever its parent is'), ('inline', 'that gets a row')):
        if fields.get(key, 'true') != 'true':
            sys.exit(f'context-packs: {where(home / "pack.md")} has {key}: {fields[key]}, but {key} takes only '
                     f'true. Leave it out for a pack {without}.')
    # A nested pack's when is its row in its parent's table, or what list shows for an optional one, so only an
    # inline pack that isn't optional goes without. The installed pack needs none: without one, it's pasted in.
    if id and 'when' not in fields and not ('inline' in fields and 'optional' not in fields):
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
                twin = path.parent / f'{entry.name}.md'
                if (folder / twin).is_file():
                    sys.exit(f'context-packs: {where(path)} holds a pack.md and sits beside {where(twin)}, so its '
                             f'index and that doc would both be {twin.as_posix()}. Rename one.')
                children.append(load(folder, pack, path.as_posix()))
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
    return Node(id, fields, rules, tuple(docs), tuple(files), tuple(children))


def installs(root, pack):
    """The ids of the packs nested in root that a sync installs: each one picked or above a picked one, and each
    one not optional whose parent is installed."""
    nested = {n.id for n in root.nested()}
    unknown = sorted(set(pack.docs) - nested)
    if unknown:
        sys.exit(f'context-packs: {pack.name} has no nested pack named {", ".join(unknown)}. '
                 f'Its nested packs: {", ".join(sorted(nested)) or "none"}. Choose from those with --docs.')
    parts = [pick.split('/') for pick in pack.docs]
    wanted = {'/'.join(p[:i]) for p in parts for i in range(1, len(p) + 1)}

    def visit(node):
        for child in node.children:
            if not child.optional or child.id in wanted:
                yield child.id
                yield from visit(child)
    return set(visit(root))


def index(node, pack):
    """Where a pack's generated index sits: pack.md for the installed pack, since no doc can have that name."""
    return PACKS / pack.name / f'{node.id or "pack"}.md'


def table(title, rows):
    """A table of (when, path) rows under its heading, or nothing without rows."""
    return (f'## {title} context\n\n| When | Read |\n|---|---|\n'
            + ''.join(f'| {when} | `{path.as_posix()}` |\n' for when, path in rows)) if rows else ''


def render(node, pack, installed):
    """The node's rules, then its table: a row for each of its docs and for each installed pack nested in it that
    gets one. The others are rendered the same way after it."""
    children = [c for c in node.children if c.id in installed]
    rows = sorted([(d.path[:-len('.md')], d.when, pack.synced / d.path) for d in node.docs]
                  + [(c.id, c.fields['when'], index(c, pack)) for c in children if c.row])
    title = f'{pack.name}/{node.id}' if node.id else pack.name
    pasted = [render(c, pack, installed) for c in children if not c.row]
    return '\n'.join(part for part in (node.rules, table(title, [r[1:] for r in rows]), *pasted) if part)


def body(root, pack, installed):
    """The installed pack's block: a row pointing at its index if it gets one, else its rules and table."""
    return table(pack.name, [(root.fields['when'], index(root, pack))]) if root.row else render(root, pack, installed)


def write(root, pack, installed, source, repo):
    """Copy the installed packs' files from source into repo, unless the pack is in repo already, and write the
    index of each installed pack that gets a row."""
    for node in [root] + [n for n in root.nested() if n.id in installed]:
        copies = [] if pack.local else [(source / path, repo / pack.synced / path) for path in node.files]
        for origin, target in copies:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(origin, target)
        if node.row:
            target = repo / index(node, pack)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(render(node, pack, installed), encoding='utf-8')
