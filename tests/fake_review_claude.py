#!/usr/bin/env python3
"""Stands in for `claude -p --output-format json` in the review tests. Appends its arguments and working directory to
$FAKE_CLAUDE_LOG, then prints $FAKE_CLAUDE_RESULT as the one result line the real command prints, or exits with
$FAKE_CLAUDE_CRASH having printed nothing."""
import json
import os
from pathlib import Path
import sys

with open(os.environ['FAKE_CLAUDE_LOG'], 'a') as log:
    log.write(json.dumps({'args': sys.argv[1:], 'cwd': str(Path.cwd())}) + '\n')
if os.environ.get('FAKE_CLAUDE_CRASH'):
    print('claude: something broke', file=sys.stderr)
    sys.exit(int(os.environ['FAKE_CLAUDE_CRASH']))
print(os.environ['FAKE_CLAUDE_RESULT'])
