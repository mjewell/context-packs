"""Context packs: where each comes from, and its content once fetched."""
from pathlib import Path
import re
import shutil
import sys
import tempfile
from typing import NamedTuple, Optional, Tuple

import origins

PACKS = Path('docs/agents/packs')
# A pack whose origin is the synced repo itself, read from its working tree.
LOCAL = '.'
FRONT = re.compile(r'---\n(.*?)\n---\n', re.DOTALL)
TIERS = ('optional', 'required')


class Pack(NamedTuple):
    """Where a pack comes from, a folder in a git repo pinned to a commit or a folder in the synced repo itself, and
    the optional doc sets the repo picked from it."""
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
        """Where the pack's doc sets sit in the synced repo: copied into its own folder, or where they are for a
        pack in that repo."""
        return Path(self.path) if self.local else PACKS / self.name


class Source(NamedTuple):
    """A pack's content, fetched into a folder holding its pack.md and doc sets."""
    pack: Pack
    folder: Path

    def available(self):
        """The pack's doc sets: each a folder holding an index.md, or a single .md file other than pack.md."""
        if (self.folder / 'agents.md').is_file():
            sys.exit(f'context-packs: {(Path(self.pack.path) / "agents.md").as_posix()} in {self.pack.origin} holds '
                     'rules under the name packs used before 0.2.0. Rename it to pack.md in the pack, or run update '
                     'to move to a version of the pack that has one.')
        folders = {p.name for p in self.folder.iterdir() if p.is_dir() and not p.name.startswith('.')}
        files = {p.stem for p in self.folder.glob('*.md') if p.name != 'pack.md'}
        for name in sorted(folders & files):
            sys.exit(f'context-packs: {self.pack.origin} has both {name}.md and {name}/ in '
                     f'{self.pack.path or "its root"}, so the doc set {name} is ambiguous. Keep one.')
        return sorted(folders | files)

    def entry(self, name):
        """A doc set's entry point, relative to the pack's folder."""
        return Path(name, 'index.md') if (self.folder / name).is_dir() else Path(f'{name}.md')

    def front(self, name):
        """A doc set's front matter: when to read it, and whether every repo gets it."""
        match = FRONT.match((self.folder / self.entry(name)).read_text(encoding='utf-8'))
        pairs = [line.split(': ', 1) for line in match.group(1).split('\n')] if match else []
        fields = dict(p for p in pairs if len(p) == 2)
        if len(fields) != len(pairs) or 'when' not in fields or fields.get('tier', 'optional') not in TIERS:
            where = (Path(self.pack.path) / self.entry(name)).as_posix()
            sys.exit(f'context-packs: {where} in {self.pack.origin} must start with front matter saying when to '
                     'read it, plus `tier: required` if every repo gets it:\n\n---\nwhen: Editing `**/*.ts`\n---')
        return fields

    def required(self):
        return [n for n in self.available() if self.front(n).get('tier') == 'required']

    def installs(self, picked):
        """The doc sets the pack installs: all of a pack in the synced repo, else the picked and required ones."""
        return self.available() if self.pack.local else sorted(set(picked) | set(self.required()))

    def copy(self, name, synced):
        if (self.folder / name).is_dir():
            shutil.copytree(self.folder / name, synced / name)
        else:
            synced.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.folder / f'{name}.md', synced / f'{name}.md')

    def body(self, names):
        rules_file = self.folder / 'pack.md'
        rules = rules_file.read_text(encoding='utf-8') if rules_file.is_file() else ''
        # The end marker has to start its own line, or the next sync can't find the block.
        if rules and not rules.endswith('\n'):
            rules += '\n'
        if not names:
            return rules
        rows = ''.join(f'| {self.front(n)["when"]} | `{(self.pack.synced / self.entry(n)).as_posix()}` |\n'
                       for n in names)
        table = f'## {self.pack.name} context\n\n| When | Read |\n|---|---|\n{rows}'
        return f'{rules}\n{table}' if rules else table


def fetch(repo, pack, stack):
    """The folder holding pack's content, fetched at its ref unless it's in the synced repo."""
    if pack.origin == LOCAL:
        folder = repo / pack.path
        if not folder.is_dir():
            sys.exit(f'context-packs: the {pack.name} pack\'s folder {pack.path} isn\'t in {repo}.')
        return folder
    into = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix='context-packs-')))
    return origins.extract(pack.origin, pack.ref, pack.path, into)
