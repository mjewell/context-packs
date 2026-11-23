#!/usr/bin/env python3
"""The review's wizard, which an agent runs one step at a time. Each command does the step's deterministic work,
keeps what it learned in the run folder, and prints what to do next, with every command to run in full. The
orchestrator starts the finders it names, each finder works through its unit with the commands its brief gives, and
the wizard refuses an answer until it's whole. A local review and a CI review run the same steps."""
import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import sys
import tempfile

REVIEW = Path(__file__).resolve().parent
# After review/, since src/ has a report.py of its own, and the wizard needs review/'s.
sys.path.append(str(REVIEW.parent / 'src'))
from blocks import instructions, region  # noqa: E402
import args as claude  # noqa: E402
from change import Change, Refused, commit, git  # noqa: E402
import report  # noqa: E402
import schema  # noqa: E402
import tables  # noqa: E402
from units import PROMPTS, RULE_KIND, UNCOVERED_KIND, sources  # noqa: E402

STATE = 'state.json'
SCHEMA = 'findings.schema.json'
GROUPS = 'groups.schema.json'
# The kinds of finding, in the order the findings schema lists them.
KINDS = claude.findings_schema()['properties']['findings']['items']['properties']['kind']['enum']
# What a finder needs beyond the skill's prompt: how to read the change, and where its answer goes. A unit's finder
# also hears how the review knows it read its docs.
SERVED = 'Read each doc only through its command, so the review knows it was read. '
FINDER = '''

{served}Read the code at the head with Read, Glob and Grep. `diff` starts each line the head has with its line number \
there: give that number as a spot's line, not a count of lines in the diff. Read every page of a path's diff before \
you judge it. {kind} Write your answer to `{answer}`, in the shape `{schema}` sets. Then run `{submit}`, and do what \
it says.'''
# What the merging agent needs beyond the skill's merge prompt.
MERGE = '''

Read the change with `{files}`, `{diff}` and `{log}`, if a spot needs checking. Answer with groups. Each group is one \
finding: the ids of the finders' findings it merges, and its kind, headline and take. Put every id in exactly one \
group. A script builds each finding's rules, spots, signs and exemplars from its group's findings. Write your groups \
to `{answer}`, in the shape `{schema}` sets. Then run `{submit}`, and do what it says.'''


def counted(count, noun):
    return f'{count} {noun}' + 's' * (count != 1)


class Run:
    """A review in progress, kept in its run folder."""

    def __init__(self, folder):
        self.folder = Path(folder)
        self.state = json.loads((self.folder / STATE).read_text(encoding='utf-8'))
        # git reads the repo the review started in, wherever the agent runs the step from.
        os.chdir(self.state['root'])

    def change(self):
        return Change(self.state['base'], self.state['head'])

    def command(self, *args):
        """A command as an agent runs it: the launcher this run was started with, its folder, and the step."""
        return ' '.join([self.state['command'], '--run', shlex.quote(str(self.folder)), *args])

    @property
    def units(self):
        return self.state['units']

    @property
    def uncovered(self):
        """The uncovered finder's number, which comes after every unit's."""
        return len(self.units)

    def finder(self, text):
        """The finder a number names, once init named it."""
        if not text.isdigit() or int(text) > self.uncovered:
            raise Refused(f'There is no finder {text}: init named finders 0 to {self.uncovered}.')
        return int(text)

    def served(self, unit):
        """The folder that marks which of a unit's docs doc printed, one empty file for each, so finders running at
        once never write the same file."""
        return self.folder / 'served' / f'unit-{unit}'

    def answer(self, finder):
        """Where a finder writes its answer."""
        return self.folder / 'answers' / f'unit-{finder}.json'

    @property
    def groups(self):
        """Where the merging agent writes its groups."""
        return self.folder / 'answers' / 'groups.json'

    @property
    def findings(self):
        """The review's findings, which submit-groups writes from the groups, so it marks that the run is done."""
        return self.folder / 'findings.json'

    @property
    def sources(self):
        """The finders' findings, numbered for the merge. next writes it once every finder is in, so it marks that the
        merge has started."""
        return self.folder / 'sources.json'

    def accepted(self, finder):
        """Where submit keeps a finder's answer once it took it, so a later edit to the answer changes nothing."""
        return self.folder / 'accepted' / f'unit-{finder}.json'

    def finders(self):
        """Each finder's number, its label, and the one-line prompt the orchestrator gives it."""
        labels = [self.units[0][0]] + [counted(len(unit), 'doc') for unit in self.units[1:]]
        named = [(n, f'unit {n}, {label}') for n, label in enumerate(labels)]
        named.append((self.uncovered, 'the uncovered finder'))
        return [(n, label, f'Run `{self.command("brief", str(n))}` and follow what it says.') for n, label in named]


def init(args):
    head = commit(args.head)
    if git('rev-parse', 'HEAD').strip() != head:
        raise Refused(f"The checkout isn't the head, {head}. Check out the head, then run init again.")
    root = Path(git('rev-parse', '--show-toplevel').strip())
    file = instructions(root)
    units = [[file.relative_to(root).as_posix()], *tables.units(root, region(root, file).block)]
    change = Change(args.base, head)
    commits = len(git('rev-list', f'{change.start}..{change.head}').split())
    folder = Path(tempfile.mkdtemp(prefix='pack-review-'))
    state = {'base': change.base, 'head': change.head, 'root': str(root), 'command': args.command, 'units': units}
    (folder / STATE).write_text(json.dumps(state), encoding='utf-8')
    (folder / 'answers').mkdir()
    shutil.copy(PROMPTS / SCHEMA, folder / SCHEMA)
    (folder / GROUPS).write_text(json.dumps(claude.groups_schema(), indent=1), encoding='utf-8')
    run = Run(folder)
    lines = [f'Reviewing {counted(commits, "commit")} that change {counted(len(change.paths()), "file")}, against '
             f'{counted(len(units), "unit")}.', '',
             f'Start these {len(run.finders())} subagents now, in one message, so they run at once. Give each exactly '
             'this prompt:']
    lines += [f'  {label}: {prompt}' for _, label, prompt in run.finders()]
    lines.append(f'When all of them have answered, run `{run.command("next")}`.')
    print('\n'.join(lines))


def brief(args):
    run = Run(args.run)
    if args.finder == 'merge':
        merge_brief(run)
        return
    finder = run.finder(args.finder)
    cmd = run.command()
    if finder == run.uncovered:
        # The uncovered finder searches every unit's docs for a rule that settles a choice, rather than reading each
        # in full, so it reads them with its own tools.
        name, kind, served = 'uncovered-prompt.md', UNCOVERED_KIND, ''
        docs = ''.join(f'- `{path}`\n' for unit in run.units for path in unit)
    else:
        name, kind, served = 'unit-prompt.md', RULE_KIND, SERVED
        docs = ''.join(f'- `{path}`: run `{run.command("doc", str(finder), str(n))}`\n'
                       for n, path in enumerate(run.units[finder], 1))
    text = (PROMPTS / name).read_text(encoding='utf-8').format(
        diff=f'what `{cmd} diff <path>` prints, one path at a time, for the paths `{cmd} files` lists',
        log=f'what `{cmd} log` prints', docs=docs.rstrip('\n'))
    print(text.rstrip('\n') + FINDER.format(served=served, kind=kind, answer=run.answer(finder),
                                            schema=run.folder / SCHEMA, submit=run.command('submit', str(finder))))


def merge_brief(run):
    if not run.sources.exists():
        raise Refused(f"The merge can't start yet: run `{run.command('next')}` to see whose answers aren't in.")
    answers = f"Every finder's findings are in `{run.sources}`, each with an id."
    text = (PROMPTS / 'merge-prompt.md').read_text(encoding='utf-8').format(answers=answers)
    print(text.rstrip('\n') + MERGE.format(files=run.command('files'), diff=run.command('diff', '<path>'),
                                           log=run.command('log'), answer=run.groups, schema=run.folder / GROUPS,
                                           submit=run.command('submit-groups')))


def doc(args):
    run = Run(args.run)
    unit = run.finder(args.unit)
    if unit == run.uncovered:
        raise Refused('The uncovered finder has no docs to read through doc: search them with Read, Glob and Grep.')
    docs = run.units[unit]
    if not args.n.isdigit() or not 1 <= int(args.n) <= len(docs):
        raise Refused(f'Unit {unit} has {counted(len(docs), "doc")}.')
    text = (Path(run.state['root']) / docs[int(args.n) - 1]).read_text(encoding='utf-8')
    run.served(unit).mkdir(parents=True, exist_ok=True)
    (run.served(unit) / str(int(args.n))).touch()
    print(text, end='')


def page(text):
    """The page a step's argument names, from 1."""
    if not text.isdigit() or int(text) < 1:
        raise Refused(f'{text!r} isn\'t a page: pages count from 1.')
    return int(text)


def files(args):
    print(Run(args.run).change().changed(), end='')


def diff(args):
    run = Run(args.run)
    change = run.change()
    if args.path not in change.paths():
        raise Refused(f"{args.path} isn't one of the paths `{run.command('files')}` lists.")
    print(change.diff(args.path, page(args.page)), end='')


def log(args):
    print(Run(args.run).change().log(page=page(args.page)), end='')


def answer(path, shape, again):
    """The text of an agent's answer, once it's JSON in the schema's shape."""
    if not path.is_file():
        raise Refused(f"Not taken: there's no answer at {path}. Write it, {again}.")
    text = path.read_text(encoding='utf-8')
    try:
        value = json.loads(text)
    except ValueError as error:
        raise Refused(f"Not taken: your answer at {path} isn't JSON: {error}. Fix it, {again}.")
    broken = schema.errors(value, shape)
    if broken:
        lines = ''.join(f'  {line}\n' for line in broken)
        raise Refused(f'Not taken: your answer at {path} breaks the schema:\n{lines}Fix it, {again}.')
    return text


def submit(args):
    run = Run(args.run)
    finder = run.finder(args.finder)
    again = f'then run `{run.command("submit", str(finder))}` again'
    if run.sources.exists():
        raise Refused("Not taken: the merge has started, so the finders' answers can't change.")
    if finder != run.uncovered:
        served = run.served(finder)
        unread = [(n, path) for n, path in enumerate(run.units[finder], 1) if not (served / str(n)).exists()]
        if unread:
            listed = ', '.join(f'{path} through `{run.command("doc", str(finder), str(n))}`' for n, path in unread)
            them = 'it' if len(unread) == 1 else 'them'
            raise Refused(f"Not taken: you didn't read {listed}. Read {them}, check the diff against {them}, update "
                          f'your answer, {again}.')
    text = answer(run.answer(finder), json.loads((run.folder / SCHEMA).read_text(encoding='utf-8')), again)
    findings = json.loads(text)['findings']
    run.accepted(finder).parent.mkdir(exist_ok=True)
    run.accepted(finder).write_text(text, encoding='utf-8')
    name = "the uncovered finder's answer" if finder == run.uncovered else f'unit {finder}'
    print(f'{name[0].upper()}{name[1:]} is in, with {counted(len(findings), "finding")}. Tell whoever started you that '
          f'{name} is in, and stop.')


def next_step(args):
    run = Run(args.run)
    if run.findings.exists():
        findings = json.loads(run.findings.read_text(encoding='utf-8'))['findings']
        kinds = [counted(sum(found['kind'] == kind for found in findings), kind) for kind in KINDS
                 if any(found['kind'] == kind for found in findings)]
        listed = ', '.join(kinds[:-1]) + ' and ' * (len(kinds) > 1) + kinds[-1] if kinds else ''
        print(f'Done: {counted(len(findings), "finding")}' + f', {listed}' * bool(listed) + f', in {run.findings}.')
        return
    if run.sources.exists():
        print("Waiting on the merge, whose groups aren't in yet. If it stopped without its groups going in, start it "
              f'again with the same prompt: Run `{run.command("brief", "merge")}` and follow what it says. When it has '
              f'answered, run `{run.command("next")}` again.')
        return
    finders = run.finders()
    waiting = [(label, prompt) for n, label, prompt in finders if not run.accepted(n).exists()]
    if waiting:
        lines = [f"Waiting on {counted(len(waiting), 'finder')}, whose answers aren't in yet:"]
        lines += [f'  {label}: {prompt}' for label, prompt in waiting]
        lines.append('If one of them stopped without its answer going in, start it again with the same prompt. '
                     f'When they have all answered, run `{run.command("next")}` again.')
        print('\n'.join(lines))
        return
    found = sources(run.accepted(0).parent)
    run.sources.write_text(json.dumps(found, ensure_ascii=False), encoding='utf-8')
    print(f'All {len(finders)} finders are in, with {counted(len(found), "finding")}.\n'
          f'Start one subagent with exactly this prompt: Run `{run.command("brief", "merge")}` and follow what it '
          f'says.\nWhen it has answered, run `{run.command("next")}`.')


def submit_groups(args):
    run = Run(args.run)
    if not run.sources.exists():
        raise Refused(f"Not taken: the merge hasn't started. Run `{run.command('next')}` to see whose answers aren't "
                      'in.')
    again = f'then run `{run.command("submit-groups")}` again'
    answer(run.groups, json.loads((run.folder / GROUPS).read_text(encoding='utf-8')), again)
    try:
        findings = report.findings_in(run.groups, run.sources)
    except report.Rejected as rejected:
        raise Refused(f'Not taken: {rejected}. Fix your groups, {again}.')
    built = {'base': run.state['base'], 'head': run.state['head'], 'findings': findings}
    run.findings.write_text(json.dumps(built, ensure_ascii=False), encoding='utf-8')
    print(f'{counted(len(findings), "finding")} are in {run.findings}. Tell whoever started you, and stop.')


def main(argv=None):
    parser = argparse.ArgumentParser(prog='review', description=__doc__, allow_abbrev=False)
    parser.add_argument('--run', help='the run folder init made')
    steps = parser.add_subparsers(dest='step', required=True)
    first = steps.add_parser('init', allow_abbrev=False, help='start a review of a change, in a new run folder')
    first.add_argument('--base', required=True, help='the commit or branch the change starts from')
    first.add_argument('--head', required=True, help='the commit or branch that is reviewed, checked out')
    first.add_argument('--command', required=True, help='how an agent runs the wizard, such as '
                                                        '"npx context-packs@0.11.0 review"')
    second = steps.add_parser('brief', allow_abbrev=False, help="print one finder's prompt")
    second.add_argument('finder', help="the finder's number, as init lists them, or merge")
    third = steps.add_parser('doc', allow_abbrev=False, help="print one of a unit's docs")
    third.add_argument('unit', help="the unit's number")
    third.add_argument('n', help="the doc's number in the unit's brief")
    steps.add_parser('files', allow_abbrev=False, help='list the paths the change touches')
    fourth = steps.add_parser('diff', allow_abbrev=False, help="print one path's diff, numbered")
    fourth.add_argument('path', help='a path files lists')
    fourth.add_argument('page', nargs='?', default='1', help='which page, from 1')
    fifth = steps.add_parser('log', allow_abbrev=False, help="print the change's commits")
    fifth.add_argument('page', nargs='?', default='1', help='which page, from 1')
    sixth = steps.add_parser('submit', allow_abbrev=False, help="check a finder's answer and take it")
    sixth.add_argument('finder', help="the finder's number")
    steps.add_parser('next', allow_abbrev=False, help='print what to do now')
    steps.add_parser('submit-groups', allow_abbrev=False,
                     help="check the merging agent's groups and build the findings")
    args = parser.parse_args(argv)
    if args.step != 'init' and not args.run:
        parser.error(f'{args.step} needs --run, the run folder init made')
    try:
        {'init': init, 'brief': brief, 'doc': doc, 'files': files, 'diff': diff, 'log': log, 'submit': submit,
         'next': next_step, 'submit-groups': submit_groups}[args.step](args)
    except Refused as refused:
        sys.exit(str(refused))


if __name__ == '__main__':
    main()
