"""Evaluate a pack installed in a repo. A doc's tests sit in the .evals folder of the pack holding the doc, those for
<pack>/<doc>.md in <pack>/.evals/<doc>/: a folder for each case, in claude plugin eval's format, and a triggers.md
listing prompts that should and shouldn't make an agent read the doc. Each case runs with the repo's instructions as
a sync writes them, then again with the doc left out of the pack, and the scores are compared; each trigger runs only
with the doc. The sync skips .evals, since it skips every name starting with a dot."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import re
import shutil
import sys
import tempfile
from typing import List, NamedTuple, Optional

import harness
import progress
import sync
import tree

EVALS = '.evals'
CASE_FILES = ('prompt.md', 'case.yaml')
TRIGGERS = 'triggers.md'
SECTIONS = {'## Reads': 'reads', '## Skips': 'skips'}
# What a trigger's run gets unless its triggers.md's front matter says otherwise: enough turns to read the docs a
# real repo's tables point at before settling, and tools that look but change nothing.
DEFAULTS = (('max_turns', '10'), ('allowed_tools', '[Read, Glob, Grep]'))
# Runs default to a small model, since every case runs several times and a pack can have many; --model picks another.
MODEL = 'haiku'
POOL = 4
PAUSE = 5
TRIGGERS_FORMAT = ('A triggers.md holds `## Reads` and `## Skips` headings, each followed by `- ` items, one prompt '
                   'each, with any further lines of a prompt indented under it.')


class Job(NamedTuple):
    """A case to run for a doc, with the doc or without it, and the folder holding that version of the repo."""
    doc: str
    case: Path
    variant: str
    files: Path


class Tests(NamedTuple):
    cases: List[Path]
    triggers: Optional[Path]


def tests(root, folder):
    """Each doc's tests, by the doc's path in the pack, from the .evals folders of the pack and those nested in it."""
    found = {}

    def doc_for(path, docs, home, node):
        """The doc a case folder or triggers.md tests, named by the folder holding it."""
        doc = (Path(node.id) / f'{path.parent.relative_to(home)}.md').as_posix()
        if path.parent == home or doc not in docs:
            sys.exit(f'context-packs: {path.relative_to(folder).as_posix()} should test a doc of the pack, but '
                     f'{doc} isn\'t one. A doc\'s tests go in {EVALS}/<doc>/ beside it.')
        return doc

    for node in [root, *root.nested()]:
        home = folder / node.id / EVALS
        docs = {d.path for d in node.docs}
        for case in sorted({p.parent for p in home.rglob('*') if p.name in CASE_FILES}):
            found.setdefault(doc_for(case, docs, home, node), Tests([], None)).cases.append(case)
        for triggers in sorted(home.rglob(TRIGGERS)):
            doc = doc_for(triggers, docs, home, node)
            found[doc] = found.setdefault(doc, Tests([], None))._replace(triggers=triggers)
    return found


def parse(path, where):
    """A triggers.md's front matter lines and its triggers, each a section and a prompt."""
    text = path.read_text(encoding='utf-8')
    match = tree.FRONT.match(text)
    front = match.group(1).split('\n') if match else []
    start = match.end() if match else 0
    triggers, section, item = [], None, None

    def fail(number, why):
        sys.exit(f'context-packs: {where}:{number} {why}. {TRIGGERS_FORMAT}')

    for number, line in enumerate(text[start:].split('\n'), text[:start].count('\n') + 1):
        if not line.strip():
            if item is not None:
                item.append('')
        elif line in SECTIONS:
            section, item = SECTIONS[line], None
        elif line.startswith('#'):
            fail(number, f'has the heading `{line}`, which isn\'t `## Reads` or `## Skips`')
        elif line == '-' or line.startswith('- '):
            if section is None:
                fail(number, 'has a trigger before any heading')
            if not line[2:].strip():
                fail(number, 'has an empty trigger')
            item = [line[2:].strip()]
            triggers.append((section, item))
        elif line.startswith('  ') and item is not None:
            item.append(line[2:])
        else:
            fail(number, 'has a line that isn\'t a heading, a trigger or indented under one')
    if not triggers:
        sys.exit(f'context-packs: {where} has no triggers. {TRIGGERS_FORMAT}')
    return front, [(section, '\n'.join(item).strip('\n')) for section, item in triggers]


def trigger_cases(path, where, doc, into):
    """Write a case for each trigger in the triggers.md at path into the folder into, passing when the run reads
    the doc at the path doc in its working directory, or doesn't, as the trigger's section expects."""
    front, triggers = parse(path, where)
    keys = {line.split(':', 1)[0] for line in front if re.match(r'\w+:', line)}
    lines = front + [f'{key}: {value}' for key, value in DEFAULTS if key not in keys]
    # claude plugin eval matches input_match against the tool's input as JSON, so the path is bounded by the quote
    # ending it and by the quote or slash before it.
    pattern = '["/]' + re.sub(r'([.^$*+?()\[\]{}|\\])', r'\\\1', doc).replace("'", "''") + '"'
    counts = {section: 0 for section in SECTIONS.values()}
    cases = []
    for section, prompt in triggers:
        counts[section] += 1
        words = re.findall(r'[a-z0-9]+', prompt.split('\n')[0].lower())[:6]
        case = into / '-'.join([section, str(counts[section]), *words])
        (case / 'graders').mkdir(parents=True)
        (case / 'prompt.md').write_text('---\n' + '\n'.join(lines) + f'\n---\n\n{prompt}\n', encoding='utf-8')
        # min defaults to 1, so a trigger expecting no read needs both bounds.
        bounds = 'min: 1' if section == 'reads' else 'min: 0\nmax: 0'
        (case / 'graders' / 'read.md').write_text(
            f"---\ntype: tool_used\ntool: Read\ninput_match: '{pattern}'\n{bounds}\n---\n", encoding='utf-8')
        cases.append(case)
    return cases


def scheduling(options):
    """The options to pass each run of claude plugin eval, with --model added unless they name one, how many runs
    go on at once, and the model. -j and --concurrency come out of them, since eval runs cases side by side itself."""
    passed, pool, model = [], POOL, None
    rest = iter(options)
    for option in rest:
        flag, equals, value = option.partition('=')
        if flag in ('-j', '--concurrency') or (flag.startswith('-j') and flag[2:].isdigit()):
            value = flag[2:] if flag.startswith('-j') and flag[2:] else value if equals else next(rest, '')
            if not value.isdigit() or int(value) < 1:
                sys.exit(f'context-packs: {option} needs a number of runs to go on at once, 1 or more.')
            pool = int(value)
            continue
        passed.append(option)
        if flag == '--model':
            model = value if equals else next(rest, None)
            if model is None:
                sys.exit('context-packs: --model needs a model to run on.')
            if not equals:
                passed.append(model)
    if model is None:
        model = MODEL
        passed += ['--model', MODEL]
    return passed, pool, model


def render(repo, file, found, packs, folders, imported, into):
    """Write the repo's instructions file into the folder into as a sync writes it from the packs' content in
    folders, with every file its tables point at, and return the packs as written. A pack read from a folder outside
    the repo is copied in like a pack from git, since a run's working directory holds nothing outside it, so its rows
    point at the copies."""
    into.mkdir(parents=True)
    inside = repo.resolve()
    rendered = [p._replace(origin=(repo / p.origin).resolve().as_uri())
                if p.local and inside not in [path, *path.parents] else p
                for p, path in ((p, (repo / p.synced).resolve()) for p in packs)]
    roots = {p.name: tree.load(folders[p.name], p, imported=imported.get(p.name)) for p in rendered}
    text, _ = sync.write(into, found, rendered, folders, roots)
    for pack in (p for p in rendered if p.local):
        root = roots[pack.name]
        for node in [root, *root.nested()]:
            for path in node.files:
                target = into / pack.synced / path
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(folders[pack.name] / path, target)
    (into / file.name).write_text(text, encoding='utf-8')
    return rendered


def evaluate(repo, file, found, packs, folders, imported, name, doc, options):
    """Run the tests for doc in the pack named name, or for every doc of it that has tests, and print each case's
    score with and without the doc, and each trigger's score. imported holds the packs the import packs name, by the
    pack holding each."""
    pack = next((p for p in packs if p.name == name), None)
    if not pack:
        sys.exit(f'context-packs: {name} is an import pack, and eval runs the tests of a pack installed in AGENTS.md, '
                 'which an import pack\'s tests don\'t sync with. Install the pack on its own in an empty folder, '
                 'and run eval there.')
    root = tree.load(folders[name], pack, imported=imported.get(name))
    by_doc = tests(root, folders[name])
    if doc:
        if f'{doc}.md' not in by_doc:
            sys.exit(f'context-packs: {name} has no tests for {doc}. Docs with tests: '
                     f'{", ".join(d[:-len(".md")] for d in sorted(by_doc)) or "none"}.')
        by_doc = {f'{doc}.md': by_doc[f'{doc}.md']}
    if not by_doc:
        sys.exit(f'context-packs: {name} has no tests. A doc\'s tests go in {EVALS}/<doc>/ beside it.')

    # Kept, so the reports and transcripts claude plugin eval writes into each plugin stay readable.
    work = Path(tempfile.mkdtemp(prefix='context-packs-eval-'))
    full = work / 'full'
    run_pack = next(p for p in render(repo, file, found, packs, folders, imported, full) if p.name == name)
    jobs = []
    for path, doc_tests in sorted(by_doc.items()):
        slug = path[:-len('.md')].replace('/', '-')
        triggers = trigger_cases(doc_tests.triggers, doc_tests.triggers.relative_to(folders[name]).as_posix(),
                                 (run_pack.synced / path).as_posix(),
                                 work / 'triggers' / slug) if doc_tests.triggers else []
        if doc_tests.cases:
            content = work / 'packs' / slug
            shutil.copytree(folders[name], content, ignore=shutil.ignore_patterns('.*'))
            (content / path).unlink()
            without = work / f'without-{slug}'
            render(repo, file, found, packs, {**folders, name: content}, imported, without)
            jobs += [Job(path, case, 'without', without) for case in doc_tests.cases]
        jobs += [Job(path, case, 'with', full) for case in doc_tests.cases + triggers]

    passed, pool, model = scheduling(options)
    print(f'{name}: {len(jobs)} cases on {model}, {pool} at a time')
    doc_width = max(len(job.doc) for job in jobs)
    case_width = max(len(job.case.name) for job in jobs)
    checklist = progress.Checklist([f'{job.doc.ljust(doc_width)}  {job.case.name.ljust(case_width)}  '
                                    f'{job.variant} the doc' for job in jobs])
    progress.pause(PAUSE)

    def run(index):
        checklist.start(index)
        job = jobs[index]
        # A plugin for each case, so each case's score arrives as soon as its own runs finish.
        plugin = harness.plugin(work / 'plugins' / f'{index}-{job.case.name}', job.files, file.name, [job.case])
        return harness.run(plugin, passed)

    scores = {}
    with ThreadPoolExecutor(pool) as executor:
        futures = {executor.submit(run, index): index for index in range(len(jobs))}
        try:
            for future in as_completed(futures):
                index = futures[future]
                job, result = jobs[index], future.result()
                [(case_name, score)] = result.items()
                got = scores.setdefault((job.doc, job.variant), {})
                if case_name in got:
                    sys.exit(f'context-packs: more than one test of {job.doc} is named {case_name}, so their scores '
                             'can\'t be told apart. Give each its own name.')
                got[case_name] = score
                checklist.tick(index, f'{score.score:.2f}')
        except BaseException:
            for pending in futures:
                pending.cancel()
            raise
    print()

    for path in sorted(by_doc):
        with_doc, without_doc = scores.get((path, 'with'), {}), scores.get((path, 'without'), {})
        print(f'{name}/{path}')
        if without_doc:
            # Without first, so each change is what the doc does to the score.
            for line in harness.compare(['Without', 'With'],
                                        [without_doc, {n: with_doc[n] for n in without_doc}]):
                print(line)
        triggered = {n: s for n, s in with_doc.items() if n not in without_doc}
        if triggered:
            for line in harness.compare(['Score'], [triggered], 'Trigger'):
                print(line)
        print()
    print(f'Reports and transcripts: {work}')
