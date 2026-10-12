"""Run `claude plugin eval` cases against an instructions file and the files beside it. Each run gets them through a
plugin whose SessionStart hook copies the files into the run's working directory and gives the run the instructions
as context, framed the way Claude Code frames an instructions file, since the eval harness doesn't load one from
the working directory. Knows nothing of packs."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import List, NamedTuple

FRAMING = ('Codebase and user instructions are shown below. Be sure to adhere to these instructions. IMPORTANT: These '
           'instructions OVERRIDE any default behavior and you MUST follow them exactly as written.\n\n'
           'Contents of {name} (project instructions, checked into the codebase):\n\n')
HOOK = 'cp -R "${CLAUDE_PLUGIN_ROOT}/files/." . && cat "${CLAUDE_PLUGIN_ROOT}/context.json"'


class Score(NamedTuple):
    """A case's score, the errors its runs hit, the explanations of the graders that failed, each with its run's
    number, and the report claude plugin eval wrote."""
    score: float
    errors: List[str]
    failures: List[str]
    report: Path


def plugin(into, files, name, cases):
    """Write a plugin into the folder into whose runs start with the folder files in their working directory and
    the instructions file name in it as context, holding the case folders in cases. Returns into."""
    (into / '.claude-plugin').mkdir(parents=True)
    (into / '.claude-plugin' / 'plugin.json').write_text(json.dumps({
        'name': 'context-packs-eval', 'version': '0.0.0',
        'description': 'Puts an instructions file and the files beside it in each eval run'}))
    (into / 'hooks').mkdir()
    (into / 'hooks' / 'hooks.json').write_text(json.dumps(
        {'hooks': {'SessionStart': [{'hooks': [{'type': 'command', 'command': HOOK}]}]}}))
    shutil.copytree(files, into / 'files')
    context = FRAMING.format(name=name) + (files / name).read_text(encoding='utf-8')
    (into / 'context.json').write_text(json.dumps(
        {'hookSpecificOutput': {'hookEventName': 'SessionStart', 'additionalContext': context}}))
    for case in cases:
        shutil.copytree(case, into / 'evals' / case.name)
    return into


def run(folder, options):
    """Run the cases of the plugin in folder with claude plugin eval, passing it options, and return each case's
    score by name."""
    result, report = folder / 'result.json', folder / 'report.html'
    # No baseline arm: the runs to compare are the plugins' own. A threshold of 0 leaves the exit code to failures.
    command = ['claude', 'plugin', 'eval', str(folder), '--ablation', 'none', '--trust-plugin', '--no-publish',
               '--threshold', '0', '--json', str(result), '--report', str(report), *options]
    # Captured, since runs go on side by side and their output would interleave.
    finished = subprocess.run(command, capture_output=True, text=True)
    if finished.returncode != 0 or not result.is_file():
        sys.exit(f'context-packs: claude plugin eval failed for {folder}:\n'
                 f'{(finished.stdout + finished.stderr).strip()}')
    cases = json.loads(result.read_text())['cases']
    names = [c['name'] for c in cases]
    repeated = sorted({n for n in names if names.count(n) > 1})
    if repeated:
        sys.exit(f'context-packs: more than one case in {folder / "evals"} is named {", ".join(repeated)}, so their '
                 'scores can\'t be told apart. Give each case its own name.')
    def runs(case):
        return [(number, run) for arm in case['arms'].values() for number, run in enumerate(arm, 1)]
    return {c['name']: Score(c['aggregates']['score'],
                             [f'run {n}: {run["error"]}' for n, run in runs(c) if run.get('error')],
                             [f'run {n}: {grader["explanation"]}' for n, run in runs(c)
                              for grader in run.get('graders', []) if not grader['passed']],
                             report)
            for c in cases}


def compare(labels, scores, heading='Case'):
    """Lines comparing each case's score across runs, one column per label, with each later run's change from the
    first. Under a case short of 1 in the last column go its failed graders' explanations and its report, and under
    any case go the errors its runs hit: a low score in an earlier column, such as without a doc, is the expected
    one, but an error there can still void the comparison."""
    names = sorted(scores[0])
    width = max(len(n) for n in names + [heading])
    lines = ['  ' + '  '.join([heading.ljust(width), *(label.rjust(7) for label in labels),
                               *[' Change'] * (len(labels) > 1)])]
    for name in names:
        row = [s[name].score for s in scores]
        lines.append('  ' + '  '.join([name.ljust(width), *(f'{score:7.2f}' for score in row),
                                       *(f'{score - row[0]:+7.2f}' for score in row[1:])]))
        last = scores[-1][name]
        explained = last.failures if last.score < 1 else []
        errors = [f'{label.lower()}: {error}' if len(labels) > 1 else error
                  for label, s in zip(labels, scores) for error in s[name].errors]
        lines += [f'    {note}' for note in explained + errors]
        if explained or errors:
            lines.append(f'    report: {last.report}')
    return lines
