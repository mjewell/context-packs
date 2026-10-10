"""The context-packs blocks in AGENTS.md, and the doc sets each pack installed beside them."""
import hashlib
import re
import sys
from typing import Dict, List, NamedTuple

from packs import LOCAL, PACKS, Pack

HEADER = 'header'
HEADER_START = '<!-- context-packs:start header -->\n'
HEADER_RULES = (
    '## Context Packs\n\n'
    'Context packs bring shared rules and docs in from elsewhere. Each pack has a block in this file holding its rules '
    "and a table of its context docs. Before starting work that a row in a pack's table matches, read its doc. "
    f"A pack's block, and any of its docs under `{PACKS.as_posix()}/`, are copied from the `from` and `path` in the "
    "block's start marker: change them there, never here.\n")
BLOCK = re.compile(r'^<!-- context-packs:start (\S+)((?: \S+)*) -->\n(.*?)'
                   r'^<!-- context-packs:end sha256:([0-9a-f]{12}) -->\n?', re.MULTILINE | re.DOTALL)


class Region(NamedTuple):
    """Where AGENTS.md's context-packs blocks sit, each block's text by name, the packs they hold, and the doc sets
    each installed."""
    text: str
    start: int
    end: int
    blocks: Dict[str, str]
    packs: List[Pack]
    installed: Dict[str, List[str]]


def digest(body, docs=b''):
    return hashlib.sha256(body.encode() + docs).hexdigest()[:12]


def block(start, body, docs=b''):
    return f'{start}{body}<!-- context-packs:end sha256:{digest(body, docs)} -->\n'


def snapshot(folder):
    """The synced docs' paths and contents, which the block's hash covers so edits to them are caught too."""
    if not folder.is_dir():
        return b''
    return b''.join(f'{p.relative_to(folder).as_posix()}\0'.encode() + p.read_bytes() + b'\0'
                    for p in sorted(folder.rglob('*')) if p.is_file())


def installed(repo, folder):
    """The doc sets copied into folder: each a folder holding an index.md, or a single .md file."""
    if not (repo / folder).is_dir():
        return []
    names = []
    for entry in (repo / folder).iterdir():
        if (entry / 'index.md').is_file():
            names.append(entry.name)
        elif entry.is_file() and entry.suffix == '.md':
            names.append(entry.stem)
        else:
            sys.exit(f'context-packs: {(folder / entry.name).as_posix()} is not a doc set, since it\'s neither a '
                     '.md file nor a folder with an index.md. Remove it, then sync again.')
    return sorted(names)


def marked_pack(agents_md, name, marker):
    pairs = [field.split('=', 1) for field in marker.split()]
    fields = dict(p for p in pairs if len(p) == 2)
    origin = fields.get('from')
    if (len(fields) != len(pairs) or set(fields) - {'from', 'path', 'ref'} or not origin
            or (origin == LOCAL) == ('ref' in fields)):
        sys.exit(f'context-packs: {agents_md}: the {name} block\'s start marker needs from=<git URL> and '
                 'ref=<tag or commit>, or from=. for a pack in this repo, plus path=<folder> unless the pack is the '
                 'whole repo. '
                 'Fix the marker, then sync again.')
    return Pack(name, origin, fields.get('path', ''), fields.get('ref'))


def region(repo):
    """AGENTS.md's context-packs blocks, after checking that nothing in them was edited since the last sync."""
    agents_md = repo / 'AGENTS.md'
    if agents_md.is_symlink():
        sys.exit(f'context-packs: {agents_md} is a symlink, and the sync would write through it. '
                 'Delete it, then sync again to get a real file.')
    # Bytes, so Python doesn't quietly turn the repo's CRLF line endings into LF.
    text = agents_md.read_bytes().decode('utf-8') if agents_md.exists() else block(HEADER_START, '')
    if '\r' in text:
        sys.exit(f'context-packs: {agents_md} has CRLF line endings. Convert it to LF, then sync again.')
    blocks = list(BLOCK.finditer(text))
    if not blocks:
        sys.exit(f'context-packs: {agents_md} has no context-packs blocks. '
                 f'Add these two lines where the shared rules should go, then sync again:\n\n{block(HEADER_START, "")}')
    names = [match.group(1) for match in blocks]
    if names[0] != HEADER:
        sys.exit(f'context-packs: {agents_md}: the context-packs blocks must start with the header block. '
                 f'Add these two lines before them, then sync again:\n\n{block(HEADER_START, "")}')
    for name in sorted({n for n in names if names.count(n) > 1}):
        sys.exit(f'context-packs: {agents_md} has more than one {name} block. Delete all but one, then sync again.')
    for before, after in zip(blocks, blocks[1:]):
        if text[before.end():after.start()] != '\n':
            sys.exit(f'context-packs: {agents_md} has text between the context-packs blocks, which must sit together '
                     'separated by blank lines. Move it outside them, then sync again.')
    packs = [marked_pack(agents_md, m.group(1), m.group(2)) for m in blocks[1:]]
    copied = {p.name for p in packs if not p.local}
    if (repo / PACKS).is_dir():
        for entry in sorted((repo / PACKS).iterdir()):
            if entry.name not in copied:
                sys.exit(f'context-packs: {(PACKS / entry.name).as_posix()} has no block in {agents_md} for a pack '
                         'copied from another repo. Remove it, then sync again.')
    current = {p.name: installed(repo, p.synced) for p in packs if not p.local}
    for match in blocks:
        name, _, synced, sha = match.groups()
        if digest(synced, snapshot(repo / PACKS / name) if name in copied else b'') != sha:
            sys.exit(f'context-packs: {agents_md}: the {name} block or a doc in {PACKS / name} was edited since '
                     'the last sync. Move the change into its context pack or outside them, revert it, '
                     'then sync again.')
    return Region(text, blocks[0].start(), blocks[-1].end(), {m.group(1): m.group(0) for m in blocks}, packs,
                  current)
