"""Run each doc's cases: prompts under `## Reads` that should make an agent read the doc, and under `## Skips` that
shouldn't. Each runs as a `claude -p` session in a copy of the repo, and passes on whether the session read the doc."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import NamedTuple

HEADING = re.compile(r'^## (Reads|Skips)$')


class Case(NamedTuple):
    """A prompt, and whether a session given it should read the doc at path, relative to the repo."""
    name: str
    path: Path
    expect: str
    prompt: str


def packs(root, repo):
    """Each pack read in place, as the pack, a node of it, and the folder holding its content."""
    from packs import REPO
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
                for expect, prompt in parse(file.read_text(encoding='utf-8'), os.path.relpath(file, repo)):
                    yield Case(name, pack.synced / doc.path, expect, prompt)


def session(prompt, cwd, model):
    """The files a claude -p session given prompt in cwd read, resolved."""
    command = ['claude', '-p', prompt, '--output-format', 'stream-json', '--verbose', '--setting-sources', 'project',
               '--allowedTools', 'Read,Glob,Grep', '--max-turns', '8', *(['--model', model] if model else [])]
    output = subprocess.run(command, cwd=cwd, capture_output=True, text=True).stdout
    read = set()
    for line in output.splitlines():
        message = json.loads(line)
        if message.get('type') != 'assistant':
            continue
        for part in message['message']['content']:
            if part.get('type') == 'tool_use' and part['name'] == 'Read':
                read.add(Path(part['input']['file_path']).resolve())
    return read


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
    with tempfile.TemporaryDirectory(prefix='context-packs-eval-') as temp:
        copy = Path(temp) / 'repo'
        shutil.copytree(repo, copy, symlinks=True, ignore=shutil.ignore_patterns('.git', 'node_modules', '.evals'))
        runs = [case for case in found for _ in range(args.runs)]
        with ThreadPoolExecutor(4) as pool:
            reads = list(pool.map(lambda case: session(case.prompt, copy, args.model), runs))
        failed = 0
        for index, case in enumerate(found):
            # A prompt passes only if every run of it does, so a when that matches some of the time shows up.
            passes = sum(((copy / case.path).resolve() in read) == (case.expect == 'reads')
                         for read in reads[index * args.runs:(index + 1) * args.runs])
            passed = passes == args.runs
            failed += not passed
            count = f'{passes}/{args.runs}  ' if args.runs > 1 else ''
            first = case.prompt.split('\n')[0]
            print(f'{"✓" if passed else "✗"} {case.name}  {case.expect}  {count}{first}')
    if failed:
        sys.exit(f'context-packs: {failed} of {len(found)} cases failed.')
