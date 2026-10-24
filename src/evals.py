"""Run each doc's cases: prompts under `## Reads` that should make an agent read the doc, and under `## Skips` that
shouldn't. Each runs as a `claude -p` session in a copy of the repo, and passes on whether the session read the doc."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import NamedTuple, Optional

import imports
from packs import GEN, REPO, ROOT, local
import tree

HEADING = re.compile(r'^## (Reads|Skips)$')
CLI = Path(__file__).resolve().parent / 'cli.py'
# What a session's copy leaves out: history, installed dependencies, and the cases it's being tested on.
LEFT_OUT = shutil.ignore_patterns('.git', 'node_modules', '.evals')


class Case(NamedTuple):
    """A prompt, and whether a session given it should read the doc at path, relative to the repo. pack is the id of
    the pack holding the doc, '' for the repo's own docs, and fixture the folder its session runs in a copy of, from a
    fixture/ beside its case file, or None for the repo."""
    name: str
    path: Path
    pack: str
    fixture: Optional[Path]
    expect: str
    prompt: str

    @property
    def copy(self):
        """Which copy the case's session runs in: the repo's, shared by every case without a fixture, or its
        fixture's with its pack installed, since a fixture stands in for another repo installing just that pack."""
        return (self.fixture, self.pack) if self.fixture else (None, None)


def packs(root, repo):
    """Each pack read in place, as the pack, a node of it, and the folder holding its content."""
    stack = [(REPO, root, repo / REPO.synced)]
    while stack:
        pack, node, source = stack.pop(0)
        if not pack.local:
            continue
        yield pack, node, source
        stack += [(pack, child, source) for child in node.children]
        stack += [(i.pack, i.root, i.source) for i in node.imports]


def parse(text, where):
    """The prompts in a doc's case file, as (expect, prompt) pairs. A prompt is a `- ` item under a `## Reads` or
    `## Skips` heading, and goes on over the lines indented under it, as a Markdown list item does. Any other line
    stops the run, so a forgotten indent can't split a prompt without a word."""
    found, expect = [], None
    for number, line in enumerate(text.split('\n'), 1):
        heading = HEADING.match(line)
        if heading:
            expect = heading.group(1).lower()
        elif expect and line.startswith('- '):
            found.append((expect, [line[2:]]))
        elif found and (line.startswith('  ') or not line.strip()):
            found[-1][1].append(line[2:])
        elif line.strip():
            sys.exit(f'context-packs: {where}:{number} is neither a `## Reads` or `## Skips` heading, a `- ` item under '
                     'one, nor a line indented under an item. Indent it under its item, or start an item with `- `.')
    return [(expect, '\n'.join(lines).rstrip('\n')) for expect, lines in found]


def cases(root, repo):
    """Every case of every doc in a pack read in place."""
    for pack, node, source in packs(root, repo):
        for doc in node.docs:
            file = source / Path(doc.path).parent / '.evals' / f'{Path(doc.path).stem}.md'
            if file.is_file():
                name = '/'.join(part for part in (pack.id, doc.path) if part)
                # Resolved, so a fixture linked from another folder's .evals/ is copied like a folder.
                fixture = (file.parent / 'fixture').resolve() if (file.parent / 'fixture').is_dir() else None
                for expect, prompt in parse(file.read_text(encoding='utf-8'), os.path.relpath(file, repo)):
                    yield Case(name, pack.synced / doc.path, pack.id, fixture, expect, prompt)


def session(prompt, cwd, model, doc):
    """The files a claude -p session given prompt in cwd read, resolved, ending it as soon as it reads doc, since
    that settles the case either way. --tools leaves it only tools that look, and --allowedTools lets it use them
    without asking; no MCP server loads, nor any settings but the copy's own."""
    command = ['claude', '-p', prompt, '--output-format', 'stream-json', '--verbose', '--setting-sources', 'project',
               '--tools', 'Read,Glob,Grep', '--allowedTools', 'Read,Glob,Grep', '--strict-mcp-config', '--max-turns', '8',
               '--model', model]
    read = set()
    with subprocess.Popen(command, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True) as process:
        for line in process.stdout:
            message = json.loads(line)
            if message.get('type') != 'assistant':
                continue
            for part in message['message']['content']:
                if part.get('type') == 'tool_use' and part['name'] == 'Read':
                    read.add(Path(part['input']['file_path']).resolve())
            if doc in read:
                process.kill()
                break
    return read


def shown(path, copy, repo):
    """A file a session read, relative to the copy or else the repo when it's in one, as a failure lists it."""
    for folder in (copy.resolve(), repo.resolve()):
        if folder in path.parents:
            return path.relative_to(folder).as_posix()
    return str(path)


def pointed(imported, repo):
    """The import pack's text, naming a folder on disk it reads by its absolute path, so its rows point at the folder
    itself from a copy of a fixture."""
    if not local(imported.origin):
        return imported.text
    front = tree.FRONT.match(imported.text)
    fields = [line for line in front.group(1).split('\n') if not line.startswith('from: ')]
    origin = os.path.normpath(repo / imported.origin)
    return '---\n' + '\n'.join([f'from: {origin}', *fields]) + '\n---\n' + imported.text[front.end():]


def stage(repo, fixture, pack, into):
    """Copy fixture into the folder into, with repo's packs synced into it. For the repo's own docs, pack '', that's
    all of context-packs/, since those docs always sit beside what the repo installs; for an imported pack, only its
    import pack, since a pack meant to be installed can't know what it will sit beside."""
    shutil.copytree(fixture, into, symlinks=True, ignore=LEFT_OUT)
    if (into / ROOT).exists():
        sys.exit(f'context-packs: {fixture} has a {ROOT.as_posix()}/ folder of its own, and eval puts this repo\'s '
                 'packs there. Remove it from the fixture.')
    found = imports.scan(repo)
    if not pack:
        shutil.copytree(repo / ROOT, into / ROOT, symlinks=True,
                        ignore=lambda folder, names: [*LEFT_OUT(folder, names), *[GEN.name] * (Path(folder) == repo / ROOT)])
    for imported in found:
        if not pack or imported.id == pack:
            (into / imported.file).parent.mkdir(parents=True, exist_ok=True)
            (into / imported.file).write_text(pointed(imported, repo), encoding='utf-8')
    synced = subprocess.run([sys.executable, str(CLI), '--dir', str(into)], capture_output=True, text=True)
    if synced.returncode != 0:
        sys.exit(f'context-packs: syncing the packs into a copy of {fixture} failed:\n{synced.stderr.strip()}')


def plural(count, noun):
    return f'{count} {noun}' + 's' * (count != 1)


def status(done, total):
    """On a terminal, how many runs have finished, on a line the next one overwrites; None clears it."""
    if sys.stdout.isatty():
        sys.stdout.write('\r\033[K' + (f'[{done}/{total}]' if done is not None else ''))
        sys.stdout.flush()


def report(case, reads, doc, copies, repo, runs):
    """Print how the case's runs went, as each read doc or didn't, and return whether every run passed, so a when
    that matches only some of the time shows up."""
    passes = sum((doc in read) == (case.expect == 'reads') for read in reads)
    passed = passes == runs
    status(None, None)
    count = f'{passes}/{runs}  ' if runs > 1 else ''
    first = case.prompt.split('\n')[0]
    print(f'{"✓" if passed else "✗"} {case.name}  {case.expect}  {count}{first}')
    if not passed:
        docs = sorted({shown(path, copies[case.copy], repo) for read in reads for path in read if path.suffix == '.md'})
        print(f'    read: {", ".join(docs)}' if docs else '    read no docs')
    sys.stdout.flush()
    return passed


def run(root, repo, args):
    found = list(cases(root, repo))
    if not found:
        sys.exit('context-packs: no doc has cases. Write the prompts for a doc in .evals/<doc>.md beside it, as `- ` '
                 'items under `## Reads` and `## Skips`.')
    names = sorted({case.name for case in found})
    unknown = [name for name in args.docs if name not in names]
    if unknown:
        sys.exit(f'context-packs: {", ".join(unknown)} has no cases. Docs with cases: {", ".join(names)}.')
    found = [case for case in found if not args.docs or case.name in args.docs]
    repo = repo.resolve()
    with tempfile.TemporaryDirectory(prefix='context-packs-eval-') as temp:
        # One copy for each fixture and pack it tests, and one of the repo for cases without a fixture, all made before
        # any session runs.
        copies = {}
        for key in dict.fromkeys(case.copy for case in found):
            copies[key] = Path(temp) / str(len(copies))
            fixture, pack = key
            if fixture:
                stage(repo, fixture, pack, copies[key])
            else:
                shutil.copytree(repo, copies[key], symlinks=True, ignore=LEFT_OUT)

        def doc(case):
            """Where the session finds the case's doc: in its copy, unless it's in a pack read in place and the copy
            is of a fixture, whose import packs point at the repo."""
            return ((repo if case.fixture and case.pack else copies[case.copy]) / case.path).resolve()

        fixtures = len({fixture for fixture, _ in copies if fixture})
        where = ' and '.join([*['a copy of the repo'] * ((None, None) in copies), *[plural(fixtures, 'fixture')] * bool(fixtures)])
        times = f', {args.runs} times each' if args.runs > 1 else ''
        print(f'Running {plural(len(found), "prompt")} for {plural(len({c.name for c in found}), "doc")}{times}, in '
              f'{where}, on {args.model}…', flush=True)
        reads = {index: [] for index in range(len(found))}
        failed = 0
        with ThreadPoolExecutor(4) as pool:
            runs = {pool.submit(session, case.prompt, copies[case.copy], args.model, doc(case)): index
                    for index, case in enumerate(found) for _ in range(args.runs)}
            for done, future in enumerate(as_completed(runs), 1):
                index = runs[future]
                reads[index].append(future.result())
                if len(reads[index]) == args.runs:
                    failed += not report(found[index], reads[index], doc(found[index]), copies, repo, args.runs)
                status(done, len(runs))
        status(None, None)
        print(f'{len(found) - failed} passed' if not failed else f'{failed} of {len(found)} failed')
    if failed:
        sys.exit(1)
