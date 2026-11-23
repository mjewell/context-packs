"""How the tests run the repo's scripts. While the code moves from Python to TypeScript, a script moves to node here,
in one line, and every test that runs it follows. The tests check what a script prints and does, never how it's
written, so the same tests check it in either language."""
from pathlib import Path
import shlex
import sys

ROOT = Path(__file__).resolve().parents[1]

# The scripts written in TypeScript so far, each by its path from the repo root without its extension, such as
# 'src/cli'. Node runs a .ts file directly, outside node_modules.
TYPESCRIPT = frozenset({'src/cli', 'review/wizard', 'review/change', 'review/report', 'review/start',
                        'review/transcript'})


def command(script):
    """The command that runs script, such as 'review/wizard', as a list of arguments."""
    if script in TYPESCRIPT:
        return ['node', str(ROOT / f'{script}.ts')]
    return [sys.executable, str(ROOT / f'{script}.py')]


def shell(script):
    """The command that runs script, as one line for a shell."""
    return ' '.join(shlex.quote(part) for part in command(script))
