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
import sys
import tempfile

REVIEW = Path(__file__).resolve().parent
sys.path.insert(0, str(REVIEW.parent / 'src'))
from blocks import instructions, region  # noqa: E402
from change import Change, Refused, commit, git  # noqa: E402
import report  # noqa: E402
import schema  # noqa: E402
import tables  # noqa: E402

# The prompts and the schema live with the pack-findings skill, since an installed skill holds only its own folder.
PROMPTS = REVIEW.parent / 'skills' / 'pack-findings'
# The sentence after a finder's prompt that names the kind of finding it reports.
RULE_KIND = 'Each rule with a deviating spot is one finding of kind `deviation`.'
UNCOVERED_KIND = 'Each choice is one finding of kind `uncovered choice`, with no rules.'
STATE = 'state.json'
# How a brief's agent runs the wizard. Claude Code refuses a command it can't check before it runs, such as one with a
# shell variable, so an agent that builds its own commands loses turns.
EXACT = 'Run each command exactly as it is printed here, one per Bash call, with no variables, `cd` or `&&` around it.'
# The kinds of finding, in the order the findings schema lists them.
KINDS = schema.findings_schema()['properties']['findings']['items']['properties']['kind']['enum']
# What a finder needs beyond the skill's prompt: how to read the change, and where its answer goes. A unit's finder
# also hears how the review knows it read its docs.
SERVED = 'Read each doc only through its command, so the review knows it was read. '
FINDER = '''{exact} {served}Read the code at the head in the current folder. `diff` starts each line the head has \
with its line number there: give that number as a spot's line, not a count of lines in the diff. Read every page of a \
path's diff before you judge it. {kind}'''
# What the merging agent needs beyond the skill's merge prompt.
MERGE = '''{exact} Read the change with `{files}`, `{diff}` and `{log}`, if a spot needs checking. Answer with \
groups. Each group is one finding: the ids of the finders' findings it merges, and its kind, headline and take. Put \
every id in exactly one group. A script builds each finding's rules, spots, signs and exemplars from its group's \
findings.'''


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
    if not change.paths():
        raise Refused(f'The change from {args.base} to {args.head} touches no files, so there is nothing to review.')
    commits = len(git('rev-list', f'{change.start}..{change.head}').split())
    folder = Path(tempfile.mkdtemp(prefix='pack-review-'))
    state = {'base': change.base, 'head': change.head, 'root': str(root), 'command': args.command, 'units': units}
    (folder / STATE).write_text(json.dumps(state), encoding='utf-8')
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
    print('\n\n'.join([text.rstrip('\n'), FINDER.format(exact=EXACT, served=served, kind=kind),
                       handing('answer', run.command('submit', str(finder)), schema.findings_schema())]))


def sources(folder):
    """Every finder's findings, from the unit-<n>.json answers in folder, numbered as <finder>:<index>, so the merging
    agent can answer with ids and a script can build each finding from the ones it names."""
    answers = sorted(Path(folder).glob('unit-*.json'), key=lambda path: int(path.stem.split('-')[1]))
    return [{'id': f"{path.stem.split('-')[1]}:{n}", 'finding': finding} for path in answers
            for n, finding in enumerate(json.loads(path.read_text(encoding='utf-8'))['findings'])]


def handing(noun, submit, shape):
    """How an agent hands its answer to the wizard, and the schema the answer fits. The answer goes in a file of the
    agent's own, and reaches the wizard on stdin, so no agent touches the run folder. It can't go in the command
    itself, nor be written to the file through the shell: Claude Code refuses a command with a brace before a quote,
    which every JSON object starts with."""
    return (f'Write your {noun} as JSON to a new file in your scratchpad, with your tool for writing files, not the '
            "shell. Then run exactly this command, with that file's path in place of `<file>`, and do what it prints:"
            f'\n\n{submit} < <file>\n\n'
            f'Your {noun} must fit this JSON Schema:\n\n{json.dumps(shape, indent=1)}')


def merging(run):
    """The run, once every finder is in and the merge has started."""
    if not run.sources.exists():
        raise Refused(f"The merge can't start yet: run `{run.command('next')}` to see whose answers aren't in.")
    return run


def merge_brief(run):
    merging(run)
    answers = f"Every finder's findings, each with an id, are what `{run.command('sources')}` prints."
    text = (PROMPTS / 'merge-prompt.md').read_text(encoding='utf-8').format(answers=answers)
    print('\n\n'.join([text.rstrip('\n'),
                       MERGE.format(exact=EXACT, files=run.command('files'), diff=run.command('diff', '<path>'),
                                    log=run.command('log')),
                       handing('groups', run.command('submit-groups'), schema.groups_schema())]))


def sources_step(args):
    print(merging(Run(args.run)).sources.read_text(encoding='utf-8'))


def doc(args):
    run = Run(args.run)
    unit = run.finder(args.unit)
    if unit == run.uncovered:
        raise Refused('The uncovered finder has no docs to read through doc: search them in the current folder.')
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


def answer(noun, submit, shape):
    """The text of the answer an agent sent on stdin, once it's JSON in the schema's shape."""
    # A terminal on stdin means no file came, and reading it would wait for typing.
    text = '' if sys.stdin.isatty() else sys.stdin.read()
    it = 'them' if noun == 'groups' else 'it'
    again = f'then submit {it} again with `{submit}`'
    if not text.strip():
        raise Refused(f'Not taken: no {noun} came on stdin. Write {it} as JSON to a file in your scratchpad, then run '
                      f"`{submit} < <file>` with that file's path.")
    try:
        value = json.loads(text)
    except ValueError as error:
        raise Refused(f"Not taken: your {noun} isn't JSON: {error}. Fix {it}, {again}.")
    broken = schema.errors(value, shape)
    if broken:
        lines = ''.join(f'  {line}\n' for line in broken)
        raise Refused(f'Not taken: your {noun} breaks the schema:\n{lines}Fix {it}, {again}.')
    return text


def submit(args):
    run = Run(args.run)
    finder = run.finder(args.finder)
    submit = run.command('submit', str(finder))
    if run.sources.exists():
        raise Refused("Not taken: the merge has started, so the finders' answers can't change.")
    if finder != run.uncovered:
        served = run.served(finder)
        unread = [(n, path) for n, path in enumerate(run.units[finder], 1) if not (served / str(n)).exists()]
        if unread:
            listed = ', '.join(f'{path} through `{run.command("doc", str(finder), str(n))}`' for n, path in unread)
            them = 'it' if len(unread) == 1 else 'them'
            raise Refused(f"Not taken: you didn't read {listed}. Read {them}, check the diff against {them}, update "
                          f'your answer, then submit it again with `{submit}`.')
    text = answer('answer', submit, schema.findings_schema())
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
        print(f'Done: {counted(len(findings), "finding")}' + f', {listed}' * bool(listed)
              + f', in {run.findings}. Here they are:\n{json.dumps(findings, ensure_ascii=False, indent=1)}')
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
    submit = run.command('submit-groups')
    groups = run.folder / 'groups.json'
    groups.write_text(answer('groups', submit, schema.groups_schema()), encoding='utf-8')
    try:
        findings = report.findings_in(groups, run.sources)
    except report.Rejected as rejected:
        raise Refused(f'Not taken: {rejected}. Fix your groups, then submit them again with `{submit}`.')
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
    sixth = steps.add_parser('submit', allow_abbrev=False, help="check a finder's answer on stdin and take it")
    sixth.add_argument('finder', help="the finder's number")
    steps.add_parser('next', allow_abbrev=False, help='print what to do now')
    steps.add_parser('sources', allow_abbrev=False, help="print the finders' findings, numbered for the merge")
    steps.add_parser('submit-groups', allow_abbrev=False,
                     help="check the merging agent's groups on stdin and build the findings")
    args = parser.parse_args(argv)
    if args.step != 'init' and not args.run:
        parser.error(f'{args.step} needs --run, the run folder init made')
    try:
        {'init': init, 'brief': brief, 'doc': doc, 'files': files, 'diff': diff, 'log': log, 'submit': submit,
         'next': next_step, 'sources': sources_step, 'submit-groups': submit_groups}[args.step](args)
    except Refused as refused:
        sys.exit(str(refused))


if __name__ == '__main__':
    main()
