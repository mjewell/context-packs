"""Run each pack's eval prompts: under `## Reads`, prompts that should make an agent read a doc, and under `## Skips`,
ones that shouldn't. A pack's prompts sit in .evals/ at its root, in a file named by the doc's path in the pack, and
run with that pack installed alone, plus everything inside it: for context-packs/, the pack at the top, that's the
whole repo. Each runs as a `claude -p` session in a copy of the pack's .evals/fixture/, or, without one, of the repo
for context-packs/ and of an empty folder for any other pack, and passes on whether the session read the doc."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import contextlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import NamedTuple

import imports
from packs import GEN, REPO, ROOT, local
import tree

HEADING = re.compile(r'^## (Reads|Skips)$')
CLI = Path(__file__).resolve().parent / 'cli.py'
MARKS = {'passed': '✓', 'failed': '✗', 'errored': '!'}
# What a session's copy leaves out: history, installed dependencies, and the prompts it's being tested on.
LEFT_OUT = shutil.ignore_patterns('.git', 'node_modules', '.evals')


class Pack(NamedTuple):
    """A pack whose prompts eval runs: its folder, relative to the repo, and whether it's context-packs/, which runs
    with the whole repo."""
    folder: Path
    top: bool

    @property
    def evals(self):
        return self.folder / '.evals'


class Case(NamedTuple):
    """A prompt, and whether a session given it should read doc, the doc at that path in the pack."""
    pack: Pack
    doc: str
    expect: str
    prompt: str

    @property
    def name(self):
        """The doc as eval prints it: by its name in the block for context-packs/, and by its path in the repo for any
        other pack, which runs on its own."""
        return self.doc if self.pack.top else (self.pack.folder / self.doc).as_posix()


def installed(root, repo):
    """context-packs/, then each pack inside it read in place: a nested pack, or a folder an import pack names."""
    yield Pack(ROOT, True)
    stack = [(REPO, child, repo / REPO.synced) for child in root.children]
    stack += [(i.pack, i.root, i.source) for i in root.imports]
    while stack:
        pack, node, source = stack.pop(0)
        if not pack.local:
            continue
        yield Pack(Path(os.path.relpath(source / node.id, repo)), False)
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
            sys.exit(f'context-packs: {where}:{number} is neither a `## Reads` or `## Skips` heading, a `- ` item '
                     'under one, nor a line indented under an item. Indent it under its item, or start an item '
                     'with `- `.')
    return [(expect, '\n'.join(lines).rstrip('\n')) for expect, lines in found]


def cases(pack, repo):
    """The prompts in the pack's .evals/, but not in its fixture."""
    evals = repo / pack.evals
    for file in sorted(evals.rglob('*.md')) if evals.is_dir() else []:
        doc = file.relative_to(evals)
        if doc.parts[0] != 'fixture':
            for expect, prompt in parse(file.read_text(encoding='utf-8'), (pack.evals / doc).as_posix()):
                yield Case(pack, doc.as_posix(), expect, prompt)


def pointed(imported, repo):
    """The import pack's text, naming a folder on disk it reads by its absolute path, so its rows point at the folder
    itself from a copy of a fixture."""
    if not local(imported.origin):
        return imported.text
    front = tree.FRONT.match(imported.text)
    fields = [line for line in front.group(1).split('\n') if not line.startswith('from: ')]
    origin = os.path.normpath(repo / imported.origin)
    return '---\n' + '\n'.join([f'from: {origin}', *fields]) + '\n---\n' + imported.text[front.end():]


def stage(repo, pack, into):
    """Write the folder the pack's sessions run in a copy of: its fixture, or else the repo for context-packs/ or an
    empty folder, with the pack synced into it alone, or with all of context-packs/ for the pack at the top. A folder
    read in place is named by its absolute path, so its rows point at the folder itself from the copy."""
    fixture = repo / pack.evals / 'fixture'
    if not fixture.is_dir() and pack.top:
        shutil.copytree(repo, into, symlinks=True, ignore=LEFT_OUT)
        return
    if fixture.is_dir():
        # Resolved, so a fixture linked from elsewhere is copied like a folder.
        shutil.copytree(fixture.resolve(), into, symlinks=True, ignore=LEFT_OUT)
        if (into / ROOT).exists():
            sys.exit(f'context-packs: {pack.evals / "fixture"} has a {ROOT.as_posix()}/ folder of its own, and eval '
                     'puts the pack it tests there. Remove it from the fixture.')
    else:
        into.mkdir()
    if pack.top:
        def left_out(folder, names):
            return [*LEFT_OUT(folder, names), *[GEN.name] * (Path(folder) == repo / ROOT)]

        shutil.copytree(repo / ROOT, into / ROOT, symlinks=True, ignore=left_out)
        for imported in imports.scan(repo):
            (into / imported.file).write_text(pointed(imported, repo), encoding='utf-8')
    else:
        (into / ROOT / name(pack)).mkdir(parents=True)
        origin = (repo / pack.folder).resolve()
        (into / ROOT / name(pack) / 'pack.md').write_text(f'---\nfrom: {origin}\n---\n', encoding='utf-8')
    synced = subprocess.run([sys.executable, str(CLI), '--dir', str(into)], capture_output=True, text=True)
    if synced.returncode != 0:
        sys.exit(f'context-packs: syncing {pack.folder} into a copy of its fixture failed:\n{synced.stderr.strip()}')


def name(pack):
    """The id a pack other than the top one gets in its copy."""
    return pack.folder.resolve().name


def docs(copy, pack):
    """Each doc the pack brings to the copy's block, by its path in the pack, with where its row points."""
    found = {}
    with contextlib.ExitStack() as stack:
        def walk(node, pack):
            for doc in node.docs:
                name = '/'.join(part for part in (pack.id, doc.path) if part)
                found[name] = (copy / pack.synced / doc.path).resolve()
            for child in node.children:
                walk(child, pack)
            for imported in node.imports:
                walk(imported.root, imported.pack)

        walk(tree.load(copy, stack), REPO)
    prefix = '' if pack.top else f'{name(pack)}/'
    return {doc[len(prefix):]: path for doc, path in found.items() if doc.startswith(prefix)}


class Run(NamedTuple):
    """How one session went: the files it read, resolved, and its error if it failed, so its reads settle nothing."""
    read: set
    error: str = None


def session(prompt, cwd, model, doc):
    """How a claude -p session given prompt in cwd went, ending it as soon as it reads doc, since that settles the
    case either way. --tools leaves it only tools that look, and --allowedTools lets it use them without asking; no
    MCP server loads, nor any settings but the copy's own."""
    command = ['claude', '-p', prompt, '--output-format', 'stream-json', '--verbose', '--setting-sources', 'project',
               '--tools', 'Read,Glob,Grep', '--allowedTools', 'Read,Glob,Grep', '--strict-mcp-config',
               '--max-turns', '8', '--model', model]
    read = set()
    with tempfile.TemporaryFile('w+') as stderr, \
            subprocess.Popen(command, cwd=cwd, stdout=subprocess.PIPE, stderr=stderr, text=True) as process:
        for line in process.stdout:
            message = json.loads(line)
            if message.get('type') == 'result':
                # claude flags running out of turns as an error too, but the session just ends there, having read
                # what it read.
                failed = message.get('is_error') and message['subtype'] != 'error_max_turns'
                return Run(read, message['result'] if failed else None)
            if message.get('type') != 'assistant':
                continue
            for part in message['message']['content']:
                if part.get('type') == 'tool_use' and part['name'] == 'Read':
                    read.add(Path(part['input']['file_path']).resolve())
            if doc in read:
                process.kill()
                return Run(read)
        process.wait()
        stderr.seek(0)
        return Run(read, stderr.read().strip() or f'claude exited with code {process.returncode} without a result')


def shown(path, copy, repo):
    """A file a session read, relative to the copy or else the repo when it's in one, as a failure lists it."""
    for folder in (copy.resolve(), repo.resolve()):
        if folder in path.parents:
            return path.relative_to(folder).as_posix()
    return str(path)


def plural(count, noun):
    return f'{count} {noun}' + 's' * (count != 1)


def status(done, total):
    """On a terminal, how many runs have finished, on a line the next one overwrites; None clears it."""
    if sys.stdout.isatty():
        sys.stdout.write('\r\033[K' + (f'[{done}/{total}]' if done is not None else ''))
        sys.stdout.flush()


def report(case, results, doc, copy, repo, runs):
    """Print how the case's runs went, as each read doc or didn't, and return 'passed' if every run did, so a when
    that matches only some of the time shows up, 'errored' if a session failed, or else 'failed'."""
    errors = list(dict.fromkeys(result.error for result in results if result.error))
    reads = [result.read for result in results if not result.error]
    passes = sum((doc in read) == (case.expect == 'reads') for read in reads)
    outcome = 'errored' if errors else 'passed' if passes == runs else 'failed'
    status(None, None)
    count = f'{passes}/{runs}  ' if runs > 1 else ''
    first = case.prompt.split('\n')[0]
    print(f'{MARKS[outcome]} {case.name}  {case.expect}  {count}{first}')
    for error in errors:
        print(f'    error: {error}')
    if outcome == 'failed':
        docs = sorted({shown(path, copy, repo) for read in reads for path in read if path.suffix == '.md'})
        print(f'    read: {", ".join(docs)}' if docs else '    read no docs')
    sys.stdout.flush()
    return outcome


def where(packs, repo):
    """What the packs' sessions run in, as the first line says it."""
    fixtures = sum((repo / pack.evals / 'fixture').is_dir() for pack in packs)
    repos = sum(pack.top and not (repo / pack.evals / 'fixture').is_dir() for pack in packs)
    empty = len(packs) - fixtures - repos
    return ', '.join([*['a copy of the repo'] * repos, *[plural(fixtures, 'fixture')] * bool(fixtures),
                      *[plural(empty, 'empty folder')] * bool(empty)])


def run(root, repo, args):
    repo = repo.resolve()
    if args.pack:
        packs = [Pack(Path(os.path.relpath((repo / args.pack).resolve(), repo)), False)]
    else:
        packs = list(installed(root, repo))
    found = [case for pack in packs for case in cases(pack, repo)]
    if not found:
        sys.exit('context-packs: no pack has eval prompts. Write the prompts for a doc in .evals/<doc>.md at the root '
                 'of its pack, as `- ` items under `## Reads` and `## Skips`.')
    names = sorted({name for case in found for name in (case.doc, case.name)})
    unknown = [doc for doc in args.docs if doc not in names]
    if unknown:
        sys.exit(f'context-packs: {", ".join(unknown)} has no eval prompts. Docs with them: '
                 f'{", ".join(sorted({case.name for case in found}))}.')
    found = [case for case in found if not args.docs or case.doc in args.docs or case.name in args.docs]
    packs = list(dict.fromkeys(case.pack for case in found))
    with tempfile.TemporaryDirectory(prefix='context-packs-eval-') as temp:
        # Every copy is made, and every prompt matched to its doc, before any session runs.
        copies, paths = {}, {}
        for pack in packs:
            copies[pack] = Path(temp) / str(len(copies))
            stage(repo, pack, copies[pack])
            paths[pack] = docs(copies[pack], pack)
        for case in found:
            if case.doc not in paths[case.pack]:
                sys.exit(f'context-packs: {case.pack.evals / case.doc} names no doc in {case.pack.folder}. Name its '
                         'file by the doc\'s path in the pack.')
        times = f', {args.runs} times each' if args.runs > 1 else ''
        print(f'Running {plural(len(found), "prompt")} for {plural(len({c.name for c in found}), "doc")}{times}, in '
              f'{where(packs, repo)}, on {args.model}…', flush=True)
        results = {index: [] for index in range(len(found))}
        outcomes = []
        with ThreadPoolExecutor(4) as pool:
            runs = {pool.submit(session, case.prompt, copies[case.pack], args.model, paths[case.pack][case.doc]):
                    index for index, case in enumerate(found) for _ in range(args.runs)}
            for done, future in enumerate(as_completed(runs), 1):
                index = runs[future]
                case = found[index]
                results[index].append(future.result())
                if len(results[index]) == args.runs:
                    outcomes.append(report(case, results[index], paths[case.pack][case.doc], copies[case.pack],
                                           repo, args.runs))
                status(done, len(runs))
        status(None, None)
        failed, errored = outcomes.count('failed'), outcomes.count('errored')
        print(summary(len(found), failed, errored))
    if failed or errored:
        sys.exit(1)


def summary(total, failed, errored):
    """The last line: how many passed, or how many failed and errored."""
    if not failed and not errored:
        return f'{total} passed'
    if not errored:
        return f'{failed} of {total} failed'
    if not failed:
        return f'{errored} of {total} errored'
    return f'{failed} of {total} failed, {errored} errored'
