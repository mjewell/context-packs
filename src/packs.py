"""Context packs: where each comes from, and its content once fetched."""
from pathlib import Path
import re
import sys
import tempfile
from typing import NamedTuple, Optional

import origins

PACKS = Path('docs/agents/packs')
# A pack whose origin is the synced repo itself, read from its working tree.
LOCAL = '.'
FRONT = re.compile(r'---\n(.*?)\n---\n', re.DOTALL)
TIERS = ('optional', 'required')


class Pack(NamedTuple):
    """Where a pack comes from: a folder in a git repo pinned to a commit, or a folder in the synced repo itself."""
    name: str
    origin: str
    path: str
    ref: Optional[str]

    def start(self):
        fields = ([f'from={self.origin}'] + [f'path={self.path}'] * bool(self.path)
                  + [f'ref={self.ref}'] * bool(self.ref))
        if any(re.search(r'\s', field) for field in fields):
            sys.exit(f'context-packs: the {self.name} pack\'s {" ".join(fields)} has whitespace, '
                     'which its marker can\'t hold.')
        return f'<!-- context-packs:start {" ".join([self.name, *fields])} -->\n'

    @property
    def synced(self):
        return PACKS / self.name


class Source(NamedTuple):
    """A pack's content, fetched into a folder holding its agents.md and doc sets."""
    pack: Pack
    folder: Path

    def available(self):
        return sorted(p.name for p in self.folder.iterdir() if p.is_dir())

    def front(self, name):
        """A doc set's front matter: when to read it, and whether every repo gets it."""
        entry = self.folder / name / 'index.md'
        match = FRONT.match(entry.read_text(encoding='utf-8'))
        pairs = [line.split(': ', 1) for line in match.group(1).split('\n')] if match else []
        fields = dict(p for p in pairs if len(p) == 2)
        if len(fields) != len(pairs) or 'when' not in fields or fields.get('tier', 'optional') not in TIERS:
            where = (Path(self.pack.path) / name / 'index.md').as_posix()
            sys.exit(f'context-packs: {where} in {self.pack.origin} must start with front matter saying when to '
                     'read it, plus `tier: required` if every repo gets it:\n\n---\nwhen: Editing `**/*.ts`\n---')
        return fields

    def required(self):
        return [n for n in self.available() if self.front(n).get('tier') == 'required']

    def body(self, names):
        rules = (self.folder / 'agents.md').read_text(encoding='utf-8')
        # The end marker has to start its own line, or the next sync can't find the block.
        body = rules + ('' if rules.endswith('\n') else '\n')
        if not names:
            return body
        rows = ''.join(f'| {self.front(n)["when"]} | `{(self.pack.synced / n / "index.md").as_posix()}` |\n'
                       for n in names)
        return f'{body}\n## {self.pack.name} context\n\n| When | Read |\n|---|---|\n{rows}'


def fetch(repo, pack, stack):
    """The folder holding pack's content, fetched at its ref unless it's in the synced repo."""
    if pack.origin == LOCAL:
        folder = repo / pack.path
        if not folder.is_dir():
            sys.exit(f'context-packs: the {pack.name} pack\'s folder {pack.path} isn\'t in {repo}.')
        return folder
    into = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix='context-packs-')))
    return origins.extract(pack.origin, pack.ref, pack.path, into)
