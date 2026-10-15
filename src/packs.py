"""Context packs: where each comes from, and its content once fetched."""
import os
from pathlib import Path, PurePosixPath
import re
import sys
import tempfile
from typing import NamedTuple, Optional

import origins

# The folder holding a repo's packs, which renders into its context-packs block, and the folder inside it the sync
# writes into.
ROOT = Path('context-packs')
GEN = ROOT / 'gen'
# A git URL, as git tells one from a path: it has a scheme, such as https:// or file://, or is scp-like, such as
# git@github.com:acme/rules.git, with a colon before any slash.
GIT_URL = re.compile(r'[A-Za-z][A-Za-z0-9+.-]*://|[^/]+:')


def folder(origin, path):
    """The folder at path in origin, normalized."""
    return Path(os.path.normpath(Path(origin, path))).as_posix()


def local(origin):
    """Whether origin is a folder on disk rather than a git URL: any path, such as . for the synced repo itself or
    ../agent-config beside it, or absolute. A local pack syncs from its working tree."""
    return not GIT_URL.match(origin)


class Pack(NamedTuple):
    """Where a pack comes from: a folder in a git repo pinned to a ref, or a folder on disk, relative to the synced
    repo. id is the folder under context-packs/ it renders at, '' for context-packs/ itself."""
    id: str
    origin: str
    path: str
    ref: Optional[str]

    @property
    def local(self):
        return local(self.origin)

    @property
    def generated(self):
        """The folder the sync writes the pack's files into, relative to the synced repo."""
        return GEN / self.id

    @property
    def synced(self):
        """Where the pack's docs sit, relative to the synced repo: copied into its generated folder, or where they are
        for a local pack."""
        return Path(folder(self.origin, self.path)) if self.local else self.generated

    def where(self, rel=''):
        """A file or folder in the pack, as an error names it."""
        if self.local:
            return (self.synced / rel).as_posix()
        return f'{(PurePosixPath(self.path) / rel).as_posix()} in {self.origin}'


REPO = Pack('', '.', ROOT.as_posix(), None)


def place(repo, pack):
    """Where the pack's content is, as an origin and the parts of a folder in it, to tell when two packs overlap."""
    if pack.local:
        return '', Path(os.path.normpath(repo / pack.synced)).parts
    return pack.origin, PurePosixPath(os.path.normpath(pack.path or '.')).parts


def overlap(a, b):
    """Whether one of two places holds the other."""
    (origin, outer), (other, inner) = sorted((a, b), key=lambda p: len(p[1]))
    return origin == other and inner[:len(outer)] == outer


def fetch(repo, pack, stack):
    """The folder holding pack's content, fetched at its ref unless it's local."""
    if pack.local:
        folder = repo / pack.synced
        if not folder.is_dir():
            sys.exit(f'context-packs: the {pack.id} pack\'s folder, {pack.synced.as_posix()}, isn\'t there, '
                     f'relative to {repo}.')
        return folder
    into = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix='context-packs-')))
    return origins.extract(pack.origin, pack.ref, pack.path, into)
