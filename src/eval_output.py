"""What eval prints: what it's about to run, how each prompt went as its runs finish, and how many passed."""
import sys

MARKS = {'passed': '✓', 'failed': '✗', 'errored': '!'}


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


def where(packs, repo):
    """What the packs' sessions run in, as the first line says it."""
    fixtures = sum((repo / pack.evals / 'fixture').is_dir() for pack in packs)
    repos = sum(pack.top and not (repo / pack.evals / 'fixture').is_dir() for pack in packs)
    empty = len(packs) - fixtures - repos
    return ', '.join([*['a copy of the repo'] * repos, *[plural(fixtures, 'fixture')] * bool(fixtures),
                      *[plural(empty, 'empty folder')] * bool(empty)])


def heading(prompts, docs, runs, packs, repo, model):
    """The first line: what's about to run, where, and on which model."""
    times = f', {runs} times each' if runs > 1 else ''
    print(f'Running {plural(prompts, "prompt")} for {plural(docs, "doc")}{times}, in {where(packs, repo)}, on '
          f'{model}…', flush=True)


def report(case, results, verdict, doc, copy, repo, runs):
    """Print how the case's runs went, with their errors, or the docs they read."""
    errors = list(dict.fromkeys(result.error for result in results if result.error))
    reads = [result.read for result in results if not result.error]
    status(None, None)
    count = f'{verdict.passes}/{runs}  ' if runs > 1 else ''
    first = case.prompt.split('\n')[0]
    print(f'{MARKS[verdict.outcome]} {case.name}  {case.expect}  {count}{first}')
    for error in errors:
        print(f'    error: {error}')
    docs = sorted({shown(path, copy, repo) for read in reads for path in read if path.suffix == '.md'})
    others = [path for path in docs if path != shown(doc, copy, repo)]
    if verdict.outcome == 'failed':
        print(f'    read: {", ".join(docs)}' if docs else '    read no docs')
    elif verdict.outcome == 'passed' and others:
        # Other docs a passing session read, since a row firing where it shouldn't shows up here first.
        print(f'    also read: {", ".join(others)}')
    sys.stdout.flush()


def summary(total, failed, errored):
    """The last line: how many passed, or how many failed and errored."""
    if not failed and not errored:
        return f'{total} passed'
    if not errored:
        return f'{failed} of {total} failed'
    if not failed:
        return f'{errored} of {total} errored'
    return f'{failed} of {total} failed, {errored} errored'
