"""Context packs: where each comes from, and its content once fetched."""
from pathlib import Path
import re
import sys
import tempfile
from typing import NamedTuple, Optional, Tuple

import origins

PACKS = Path('docs/agents/packs')


def local(origin):
    """Whether origin is a folder on disk rather than a git URL: a path relative to the synced repo, starting with a
    dot, such as . for the repo itself or ../agent-config beside it. A local pack syncs from its working tree."""
    return origin.startswith('.')


class Pack(NamedTuple):
    """Where a pack comes from, a folder in a git repo pinned to a commit or a folder on disk, and the optional nested
    packs the repo picked from it."""
    name: str
    origin: str
    path: str
    ref: Optional[str]
    docs: Tuple[str, ...] = ()

    def start(self):
        fields = ([f'from={self.origin}'] + [f'path={self.path}'] * bool(self.path)
                  + [f'ref={self.ref}'] * bool(self.ref) + [f'docs={",".join(self.docs)}'] * bool(self.docs))
        if any(re.search(r'\s', field) for field in fields):
            sys.exit(f'context-packs: the {self.name} pack\'s {" ".join(fields)} has whitespace, '
                     'which its marker can\'t hold.')
        return f'<!-- context-packs:start {" ".join([self.name, *fields])} -->\n'

    @property
    def local(self):
        return local(self.origin)

    @property
    def synced(self):
        """Where the pack's docs sit, relative to the synced repo: copied into its own folder, or where they are for
        a local pack."""
        return Path(self.origin, self.path) if self.local else PACKS / self.name


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
