"""Context packs: where each comes from, and its content once fetched."""
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import NamedTuple, Optional

import origins

PACKS = Path('docs/agents/generated')
# A git URL, as git tells one from a path: it has a scheme, such as https:// or file://, or is scp-like, such as
# git@github.com:acme/rules.git, with a colon before any slash.
GIT_URL = re.compile(r'[A-Za-z][A-Za-z0-9+.-]*://|[^/]+:')


def folder(origin, path):
    """The folder on disk a marker names for a pack read from origin's path, relative to the synced repo."""
    return Path(os.path.normpath(Path(origin, path))).as_posix()


def local(origin):
    """Whether origin is a folder on disk rather than a git URL: any path, relative to the synced repo, such as . for
    the repo itself or ../agent-config beside it, or absolute. A local pack syncs from its working tree."""
    return not GIT_URL.match(origin)


class Pack(NamedTuple):
    """Where a pack comes from: a folder in a git repo pinned to a commit, or a folder on disk. home is where the
    sync writes its files, if not docs/agents/generated/<name>: an import pack's place in the generated folder of the pack
    holding it."""
    name: str
    origin: str
    path: str
    ref: Optional[str]
    home: Optional[Path] = None

    def start(self):
        """The start marker of the block for this pack, which a marker names by the folder on disk holding it."""
        if re.search(r'\s', self.path):
            sys.exit(f'context-packs: the {self.name} pack\'s folder, {self.path}, has whitespace, which its marker '
                     'can\'t hold.')
        return f'<!-- context-packs:start {self.name} path={self.path} -->\n'

    @property
    def local(self):
        return local(self.origin)

    @property
    def generated(self):
        """The folder the sync writes the pack's files into, relative to the synced repo."""
        return self.home or PACKS / self.name

    @property
    def synced(self):
        """Where the pack's docs sit, relative to the synced repo: copied into its generated folder, or where they are
        for a local pack."""
        return Path(self.origin, self.path) if self.local else self.generated


def fetch(repo, pack, stack):
    """The folder holding pack's content, fetched at its ref unless it's local."""
    if pack.local:
        folder = repo / pack.synced
        if not folder.is_dir():
            sys.exit(f'context-packs: the {pack.name} pack\'s folder {pack.synced.as_posix()} isn\'t there, '
                     f'relative to {repo}.')
        return folder
    into = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix='context-packs-')))
    return origins.extract(pack.origin, pack.ref, pack.path, into)
