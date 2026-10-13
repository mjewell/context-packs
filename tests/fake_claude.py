#!/usr/bin/env python3
"""Stands in for `claude plugin eval` in tests. Each case's run starts the way Claude Code starts a session with the
plugin: its SessionStart hook runs in a fresh working directory. The run then "sees" what an agent would, the context
the hook gave it and every file in its working directory, and "reads" each doc whose row's `when` its prompt contains,
following rows in the indexes it reads. A regex grader passes when its pattern is in what the run saw, and a tool_used
grader counts the run's reads whose input, as JSON, matches its input_match, the way the real command does. Writes the
result JSON the real command writes, with only the fields context-packs reads."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROW = re.compile(r'^\| (.+?) \| `(.+?)` \|$', re.MULTILINE)


def front(text):
    """The front matter's fields, with quotes taken off, and the text after it."""
    match = re.match(r'---\n(.*?)\n---\n', text, re.DOTALL)
    fields = dict(line.split(': ', 1) for line in match.group(1).split('\n'))
    return {k: v[1:-1].replace("''", "'") if v.startswith("'") else v for k, v in fields.items()}, text[match.end():]


def reads(prompt, text, cwd, seen=()):
    """The files a run with this prompt reads, starting from the rows in text."""
    for when, path in ROW.findall(text):
        target = Path(cwd) / path
        if when.lower() in prompt.lower() and path not in seen and target.is_file():
            yield str(target)
            yield from reads(prompt, target.read_text(), cwd, (*seen, path))


def grade(grader, seen, read):
    """Whether the grader passes, and its explanation, worded as the real command words it."""
    fields, _ = front(grader.read_text())
    if fields['type'] == 'regex':
        found = fields['pattern'] in seen
        return found, f'/{fields["pattern"]}/ {"matched" if found else "did not match"} the run'
    assert fields['type'] == 'tool_used' and fields['tool'] == 'Read', fields
    count = sum(bool(re.search(fields['input_match'], json.dumps({'file_path': path}))) for path in read)
    low, high = int(fields.get('min', 1)), fields.get('max')
    passed = low <= count <= (int(high) if high else count)
    return passed, f'Read called {count}x (expected {low}..{high or "∞"})'


args = sys.argv[1:]
with open(os.environ['FAKE_CLAUDE_LOG'], 'a') as log:
    log.write(json.dumps(args) + '\n')
if os.environ.get('FAKE_CLAUDE_FAIL'):
    sys.exit('claude: something went wrong')
assert args[:2] == ['plugin', 'eval'], args
plugin = Path(args[2])
command = json.loads((plugin / 'hooks' / 'hooks.json').read_text())['hooks']['SessionStart'][0]['hooks'][0]['command']

cases = []
for case in sorted({p.parent for p in (plugin / 'evals').rglob('*') if p.name in ('prompt.md', 'case.yaml')}):
    _, prompt = front((case / 'prompt.md').read_text())
    with tempfile.TemporaryDirectory() as cwd:
        hook = subprocess.run(['sh', '-c', command], cwd=cwd, capture_output=True, text=True, check=True,
                              env={**os.environ, 'CLAUDE_PLUGIN_ROOT': str(plugin)})
        context = json.loads(hook.stdout)['hookSpecificOutput']['additionalContext']
        seen = context + ''.join(f'\n{path.relative_to(cwd)}\n{path.read_text()}'
                                 for path in sorted(Path(cwd).rglob('*')) if path.is_file())
        read = list(reads(prompt, context, cwd))
        graders = [(grader.stem, *grade(grader, seen, read)) for grader in sorted((case / 'graders').glob('*.md'))]
        score = float(all(passed for _, passed, _ in graders))
    named = (case / 'case.yaml').is_file() and re.search(r'^name: (.*)$', (case / 'case.yaml').read_text(), re.M)
    cases.append({'name': named.group(1) if named else case.name, 'aggregates': {'score': score},
                  'arms': {'with': [{'score': score, 'error': None,
                                     'graders': [{'name': name, 'passed': passed, 'explanation': why}
                                                 for name, passed, why in graders]}]}})

Path(args[args.index('--json') + 1]).write_text(json.dumps({'cases': cases}))
if '--report' in args:
    Path(args[args.index('--report') + 1]).write_text('<html>report</html>')
