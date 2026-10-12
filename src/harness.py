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
    score: float
    errors: List[str]


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
    result = folder / 'result.json'
    # No baseline arm: the runs to compare are the plugins' own. A threshold of 0 leaves the exit code to failures.
    command = ['claude', 'plugin', 'eval', str(folder), '--ablation', 'none', '--trust-plugin', '--no-publish',
               '--threshold', '0', '--json', str(result), *options]
    if subprocess.run(command).returncode != 0 or not result.is_file():
        sys.exit(f'context-packs: claude plugin eval failed for {folder}; its output above says why.')
    cases = json.loads(result.read_text())['cases']
    names = [c['name'] for c in cases]
    repeated = sorted({n for n in names if names.count(n) > 1})
    if repeated:
        sys.exit(f'context-packs: more than one case in {folder / "evals"} is named {", ".join(repeated)}, so their '
                 'scores can\'t be told apart. Give each case its own name.')
    return {c['name']: Score(c['aggregates']['score'],
                             [r['error'] for runs in c['arms'].values() for r in runs if r.get('error')])
            for c in cases}


def compare(labels, scores, heading='Case'):
    """Lines comparing each case's score across runs, one column per label, with each later run's change from the
    first, and any errors the runs reported."""
    names = sorted(scores[0])
    width = max(len(n) for n in names + [heading])
    lines = ['  ' + '  '.join([heading.ljust(width), *(label.rjust(7) for label in labels),
                               *[' Change'] * (len(labels) > 1)])]
    for name in names:
        row = [s[name].score for s in scores]
        lines.append('  ' + '  '.join([name.ljust(width), *(f'{score:7.2f}' for score in row),
                                       *(f'{score - row[0]:+7.2f}' for score in row[1:])]))
    lines += [f'  {name}: {error}' for s in scores for name in names for error in s[name].errors]
    return lines
