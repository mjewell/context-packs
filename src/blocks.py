"""The context-packs block in AGENTS.md or CLAUDE.md, which the sync owns along with context-packs/gen/."""
import hashlib
import os
import re
import sys
from typing import NamedTuple

from packs import GEN, ROOT

START = '<!-- context-packs:start -->\n'
HEADER = (
    '## Context Packs\n\n'
    'Context packs bring shared rules and docs in from elsewhere. Each pack has its rules and a table of its context '
    'docs here, and a doc may hold a table of its own. Before starting work that a row in any of these tables '
    f'matches, read its doc. The packs here, and everything under `{GEN.as_posix()}/`, are generated from '
    f'`{ROOT.as_posix()}/`: change them there, never here.\n')
BLOCK = re.compile(r'^<!-- context-packs:start -->\n(.*?)^<!-- context-packs:end sha256:([0-9a-f]{12}) -->\n?',
                   re.MULTILINE | re.DOTALL)
MARKER = re.compile(r'^<!-- context-packs:start', re.MULTILINE)
# A start marker holding a pack's name, as versions before one block per file wrote them.
OLD_MARKER = re.compile(r'^<!-- context-packs:start (?!-->)', re.MULTILINE)


class Region(NamedTuple):
    """Where the instructions file's context-packs block sits, and its text."""
    text: str
    start: int
    end: int
    block: str


def digest(body, docs=b''):
    return hashlib.sha256(body.encode() + docs).hexdigest()[:12]


def block(body, docs=b''):
    return f'{START}{body}<!-- context-packs:end sha256:{digest(body, docs)} -->\n'


def snapshot(folder):
    """The generated files' paths and contents, which the block's hash covers so edits to them are caught too."""
    if not folder.is_dir():
        return b''
    return b''.join(f'{p.relative_to(folder).as_posix()}\0'.encode() + p.read_bytes() + b'\0'
                    for p in sorted(folder.rglob('*')) if p.is_file())


def read(file):
    # Bytes, so Python doesn't quietly turn the repo's CRLF line endings into LF.
    return file.read_bytes().decode('utf-8')


def instructions(repo):
    """The file the sync writes: whichever of AGENTS.md and CLAUDE.md holds the block, else a new AGENTS.md. Which
    instruction file a repo uses is its call, so the sync stops for the block to be pasted into a file that exists,
    and never writes through a symlink."""
    agents_md, claude_md = repo / 'AGENTS.md', repo / 'CLAUDE.md'
    files = [f for f in (agents_md, claude_md) if f.is_file() and not f.is_symlink()]
    for file in files:
        # Checked first, since the block can't be found in a file with CRLF line endings.
        if '\r' in read(file):
            sys.exit(f'context-packs: {file} has CRLF line endings. Convert it to LF, then sync again.')
    marked = [f for f in files if MARKER.search(read(f))]
    if len(marked) > 1:
        sys.exit(f'context-packs: {agents_md} and {claude_md} both have a context-packs block. '
                 "Delete it from the one that shouldn't be synced, then sync again.")
    if marked:
        return marked[0]
    lines = block('')
    if len(files) > 1:
        sys.exit(f'context-packs: Neither {agents_md} nor {claude_md} has a context-packs block. Add these two lines '
                 f'to the one that should hold the packs, where the shared rules should go, then sync again:\n\n{lines}')
    if files:
        sys.exit(f'context-packs: {files[0]} has no context-packs block. '
                 f'Add these two lines where the shared rules should go, then sync again:\n\n{lines}')
    if agents_md.is_symlink():
        sys.exit(f'context-packs: {agents_md} is a symlink, and the sync would write through it. '
                 'Delete it, then sync again to get a real file.')
    if claude_md.is_symlink() and os.readlink(claude_md) != 'AGENTS.md':
        sys.exit(f'context-packs: {claude_md} is a symlink, and the sync won\'t write through it. '
                 'Replace it with the file it points to, or delete it, then sync again.')
    return agents_md


def region(repo, file):
    """file's context-packs block, or a new file's empty one, after checking that nothing in it or in context-packs/gen/
    was edited since the last sync."""
    text = read(file) if file.exists() else block('')
    if OLD_MARKER.search(text):
        sys.exit(f'context-packs: {file} has context-packs blocks from an older version, which kept packs in '
                 'docs/agents/. Replace everything from their first start marker to their last end marker with the two '
                 f'lines below. Move each import pack in docs/agents/, such as docs/agents/core/, to {ROOT.as_posix()}/, '
                 f'delete docs/agents/generated/, and move your own docs into {ROOT.as_posix()}/ or `add` their folder. '
                 f'Then sync again:\n\n{block("")}')
    blocks = list(BLOCK.finditer(text))
    if len(blocks) > 1:
        sys.exit(f'context-packs: {file} has more than one context-packs block. Delete all but one, then sync again.')
    if not blocks:
        sys.exit(f'context-packs: {file} has a context-packs start marker without its end marker. Replace it with '
                 f'these two lines, then sync again:\n\n{block("")}')
    match = blocks[0]
    body, sha = match.groups()
    if digest(body, snapshot(repo / GEN)) != sha:
        sys.exit(f'context-packs: {file}: the context-packs block or a file in {GEN.as_posix()} was edited since the '
                 f'last sync. Move the change into {ROOT.as_posix()}/ or outside the block, or revert it, then sync '
                 'again.')
    return Region(text, match.start(), match.end(), match.group(0))
