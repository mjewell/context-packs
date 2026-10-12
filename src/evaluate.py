"""Evaluate a pack installed in a repo: run each doc's cases with the repo's instructions as a sync writes them, then
again with that doc left out of the pack, and compare. A doc's cases sit in the .evals folder of the pack holding the
doc: those for <pack>/<doc>.md in <pack>/.evals/<doc>/<case>/, each case in claude plugin eval's format. The sync
skips .evals, since it skips every name starting with a dot."""
from pathlib import Path
import shutil
import sys
import tempfile

import harness
import sync
import tree

EVALS = '.evals'
CASE_FILES = ('prompt.md', 'case.yaml')


def cases(root, folder, installed):
    """Each doc's case folders, by the doc's path in the pack, from the installed packs' .evals folders."""
    found = {}
    for node in [root] + [n for n in root.nested() if n.id in installed]:
        home = folder / node.id / EVALS
        docs = {d.path for d in node.docs}
        for case in sorted({p.parent for p in home.rglob('*') if p.name in CASE_FILES}):
            if case.parent == home:
                sys.exit(f'context-packs: {case.relative_to(folder).as_posix()} sits in {EVALS} itself. Put it in '
                         f'{EVALS}/<doc>/, named after the doc it tests.')
            doc = (Path(node.id) / f'{case.parent.relative_to(home)}.md').as_posix()
            if doc not in docs:
                sys.exit(f'context-packs: {case.relative_to(folder).as_posix()} should test {doc}, which the pack '
                         f'doesn\'t have. A doc\'s cases go in {EVALS}/<doc>/<case>/ beside it.')
            found.setdefault(doc, []).append(case)
    return found


def render(repo, file, found, packs, folders, into):
    """Write the repo's instructions file into the folder into as a sync writes it from the packs' content in
    folders, with every file its tables point at. A pack read from a folder outside the repo is copied in like a pack
    from git, since a run's working directory holds nothing outside it, so its rows point at the copies."""
    into.mkdir(parents=True)
    inside = repo.resolve()
    rendered = [p._replace(origin=(repo / p.origin).resolve().as_uri())
                if p.local and inside not in [path, *path.parents] else p
                for p, path in ((p, (repo / p.synced).resolve()) for p in packs)]
    roots = {p.name: tree.load(folders[p.name], p) for p in rendered}
    installed = {p.name: tree.installs(roots[p.name], p) for p in rendered}
    text, _ = sync.write(into, found, rendered, folders, roots, installed)
    for pack in (p for p in rendered if p.local):
        root = roots[pack.name]
        for node in [root] + [n for n in root.nested() if n.id in installed[pack.name]]:
            for path in node.files:
                target = into / pack.synced / path
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(folders[pack.name] / path, target)
    (into / file.name).write_text(text, encoding='utf-8')


def evaluate(repo, file, found, packs, folders, name, doc, options):
    """Run the cases for doc in the pack named name, or for every doc of it that has cases, and print how each
    case's score changes with the doc left out."""
    pack = next(p for p in packs if p.name == name)
    root = tree.load(folders[name], pack)
    by_doc = cases(root, folders[name], tree.installs(root, pack))
    if doc:
        if f'{doc}.md' not in by_doc:
            sys.exit(f'context-packs: {name} has no cases for {doc}. Docs with cases: '
                     f'{", ".join(d[:-len(".md")] for d in sorted(by_doc)) or "none"}.')
        by_doc = {f'{doc}.md': by_doc[f'{doc}.md']}
    if not by_doc:
        sys.exit(f'context-packs: {name} has no cases. A doc\'s cases go in {EVALS}/<doc>/<case>/ beside it.')

    # Kept, so the reports and transcripts claude plugin eval writes into each plugin stay readable.
    work = Path(tempfile.mkdtemp(prefix='context-packs-eval-'))
    full = work / 'full'
    render(repo, file, found, packs, folders, full)
    for path, doc_cases in sorted(by_doc.items()):
        slug = path[:-len('.md')].replace('/', '-')
        without = work / f'without-{slug}'
        content = work / 'packs' / slug
        shutil.copytree(folders[name], content, ignore=shutil.ignore_patterns('.*'))
        (content / path).unlink()
        render(repo, file, found, packs, {**folders, name: content}, without)
        scores = [harness.run(harness.plugin(work / f'{slug}-{label}', files, file.name, doc_cases), options)
                  for label, files in (('with', full), ('without', without))]
        for line in harness.compare(f'{name}/{path}', ['With', 'Without'], scores):
            print(line)
        print()
    print(f'Reports and transcripts: {work}')
