#!/usr/bin/env python3
"""Stands in for `claude plugin eval` in tests. Each case's run starts the way Claude Code starts a session with the
plugin: its SessionStart hook runs in a fresh working directory. The run then "sees" what an agent would, the context
the hook gave it and every file in its working directory, and a case scores 1 when each of its graders' patterns is
in what it saw. Writes the result JSON the real command writes, with only the fields context-packs reads."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

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
    with tempfile.TemporaryDirectory() as cwd:
        hook = subprocess.run(['sh', '-c', command], cwd=cwd, capture_output=True, text=True, check=True,
                              env={**os.environ, 'CLAUDE_PLUGIN_ROOT': str(plugin)})
        seen = json.loads(hook.stdout)['hookSpecificOutput']['additionalContext'] + ''.join(
            f'\n{path.relative_to(cwd)}\n{path.read_text()}' for path in sorted(Path(cwd).rglob('*')) if path.is_file())
    patterns = [re.search(r'^pattern: (.*)$', grader.read_text(), re.MULTILINE).group(1)
                for grader in sorted((case / 'graders').glob('*.md'))]
    score = float(all(pattern in seen for pattern in patterns))
    named = (case / 'case.yaml').is_file() and re.search(r'^name: (.*)$', (case / 'case.yaml').read_text(), re.M)
    cases.append({'name': named.group(1) if named else case.name, 'aggregates': {'score': score},
                  'arms': {'with': [{'score': score, 'error': None}]}})

Path(args[args.index('--json') + 1]).write_text(json.dumps({'cases': cases}))
