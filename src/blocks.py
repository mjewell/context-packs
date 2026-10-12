"""The context-packs blocks in AGENTS.md or CLAUDE.md, and the files each pack wrote beside them."""
import hashlib
import os
import re
import sys
from typing import Dict, List, NamedTuple

from packs import PACKS, Pack, local

HEADER = 'header'
HEADER_START = '<!-- context-packs:start header -->\n'
HEADER_RULES = (
    '## Context Packs\n\n'
    'Context packs bring shared rules and docs in from elsewhere. Each pack has a block in this file holding its rules '
    'and a table of its context docs, and a doc may hold a table of its own. Before starting work that a row in any '
    f"of these tables matches, read its doc. A pack's block, and everything under `{PACKS.as_posix()}/`, are "
    "generated from the `from` and `path` in the block's start marker: change them there, never here.\n")
BLOCK = re.compile(r'^<!-- context-packs:start (\S+)((?: \S+)*) -->\n(.*?)'
                   r'^<!-- context-packs:end sha256:([0-9a-f]{12}) -->\n?', re.MULTILINE | re.DOTALL)


class Region(NamedTuple):
    """Where the instructions file's context-packs blocks sit, each block's text by name, and the packs they hold."""
    text: str
    start: int
    end: int
    blocks: Dict[str, str]
    packs: List[Pack]


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


def marked_pack(file, name, marker):
    pairs = [field.split('=', 1) for field in marker.split()]
    fields = dict(p for p in pairs if len(p) == 2)
    origin = fields.get('from')
    if (len(fields) != len(pairs) or set(fields) - {'from', 'path', 'ref', 'docs'} or not origin
            or local(origin) == ('ref' in fields)):
        sys.exit(f'context-packs: {file}: the {name} block\'s start marker needs from=<git URL> and '
                 'ref=<tag or commit>, or from=<a path starting with a dot> for a folder on disk, plus path=<folder> '
                 'unless the pack is the whole repo, and docs=<nested packs> for the optional ones picked. '
                 'Fix the marker, then sync again.')
    docs = tuple(fields['docs'].split(',')) if 'docs' in fields else ()
    return Pack(name, origin, fields.get('path', ''), fields.get('ref'), docs)


def read(file):
    # Bytes, so Python doesn't quietly turn the repo's CRLF line endings into LF.
    return file.read_bytes().decode('utf-8')


def instructions(repo):
    """The file the sync writes: whichever of AGENTS.md and CLAUDE.md holds the blocks, else a new AGENTS.md. Which
    instruction file a repo uses is its call, so the sync stops for the blocks to be pasted into a file that exists,
    and never writes through a symlink."""
    agents_md, claude_md = repo / 'AGENTS.md', repo / 'CLAUDE.md'
    files = [f for f in (agents_md, claude_md) if f.is_file() and not f.is_symlink()]
    for file in files:
        # Checked first, since the blocks can't be found in a file with CRLF line endings.
        if '\r' in read(file):
            sys.exit(f'context-packs: {file} has CRLF line endings. Convert it to LF, then sync again.')
    marked = [f for f in files if BLOCK.search(read(f))]
    if len(marked) > 1:
        sys.exit(f'context-packs: {agents_md} and {claude_md} both have context-packs blocks. '
                 "Delete them from the one that shouldn't be synced, then sync again.")
    if marked:
        return marked[0]
    lines = block(HEADER_START, '')
    if len(files) > 1:
        sys.exit(f'context-packs: Neither {agents_md} nor {claude_md} has context-packs blocks. Add these two lines '
                 f'to the one that should hold the packs, where the shared rules should go, then sync again:\n\n{lines}')
    if files:
        sys.exit(f'context-packs: {files[0]} has no context-packs blocks. '
                 f'Add these two lines where the shared rules should go, then sync again:\n\n{lines}')
    if agents_md.is_symlink():
        sys.exit(f'context-packs: {agents_md} is a symlink, and the sync would write through it. '
                 'Delete it, then sync again to get a real file.')
    if claude_md.is_symlink() and os.readlink(claude_md) != 'AGENTS.md':
        sys.exit(f'context-packs: {claude_md} is a symlink, and the sync won\'t write through it. '
                 'Replace it with the file it points to, or delete it, then sync again.')
    return agents_md


def region(repo, file):
    """file's context-packs blocks, or a new file's empty header block, after checking that nothing in them was edited since the last sync."""
    text = read(file) if file.exists() else block(HEADER_START, '')
    blocks = list(BLOCK.finditer(text))
    names = [match.group(1) for match in blocks]
    if names[0] != HEADER:
        sys.exit(f'context-packs: {file}: the context-packs blocks must start with the header block. '
                 f'Add these two lines before them, then sync again:\n\n{block(HEADER_START, "")}')
    for name in sorted({n for n in names if names.count(n) > 1}):
        sys.exit(f'context-packs: {file} has more than one {name} block. Delete all but one, then sync again.')
    for before, after in zip(blocks, blocks[1:]):
        if text[before.end():after.start()] != '\n':
            sys.exit(f'context-packs: {file} has text between the context-packs blocks, which must sit together '
                     'separated by blank lines. Move it outside them, then sync again.')
    packs = [marked_pack(file, m.group(1), m.group(2)) for m in blocks[1:]]
    if (repo / PACKS).is_dir():
        for entry in sorted((repo / PACKS).iterdir()):
            if entry.name not in names[1:]:
                sys.exit(f'context-packs: {(PACKS / entry.name).as_posix()} has no block in {file}. '
                         'Remove it, then sync again.')
    for match in blocks:
        name, _, synced, sha = match.groups()
        if digest(synced, snapshot(repo / PACKS / name)) != sha:
            sys.exit(f'context-packs: {file}: the {name} block or a doc in {PACKS / name} was edited since '
                     'the last sync. Move the change into its context pack or outside them, revert it, '
                     'then sync again.')
    return Region(text, blocks[0].start(), blocks[-1].end(), {m.group(1): m.group(0) for m in blocks}, packs)
