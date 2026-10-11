"""Context packs: where each comes from, and its content once fetched."""
from pathlib import Path
import re
import sys
import tempfile
from typing import NamedTuple, Optional, Tuple

import origins

PACKS = Path('docs/agents/packs')
# A pack whose origin is the synced repo itself, read from its working tree.
LOCAL = '.'


class Pack(NamedTuple):
    """Where a pack comes from, a folder in a git repo pinned to a commit or a folder in the synced repo itself, and
    the optional nested packs the repo picked from it."""
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
        return self.origin == LOCAL

    @property
    def synced(self):
        """Where the pack's docs sit in the synced repo: copied into its own folder, or where they are for a
        pack in that repo."""
        return Path(self.path) if self.local else PACKS / self.name


def fetch(repo, pack, stack):
    """The folder holding pack's content, fetched at its ref unless it's in the synced repo."""
    if pack.origin == LOCAL:
        folder = repo / pack.path
        if not folder.is_dir():
            sys.exit(f'context-packs: the {pack.name} pack\'s folder {pack.path} isn\'t in {repo}.')
        return folder
    into = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix='context-packs-')))
    return origins.extract(pack.origin, pack.ref, pack.path, into)
