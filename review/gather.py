#!/usr/bin/env python3
"""Run the pack-review skill headless over a range of commits, and write what it found, with the thread actions it
chose, as JSON. It knows nothing of where the PR is hosted: the range and a file of comments go in, and the findings
come out."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

PLUGIN = Path(__file__).resolve().parents[1]
SCHEMA = Path(__file__).resolve().parent / 'findings.schema.json'
# The agent reads the PR, which is untrusted text, so it gets tools that only read, confined by --restricted to the
# checkout and the comments' folder, and a shell only for git commands that read. It returns its findings as its
# answer, so it needs no tool that writes.
TOOLS = ['Read', 'Glob', 'Grep', 'Bash', 'Agent']
ALLOWED = ['Read', 'Glob', 'Grep', 'Agent', 'Bash(git diff:*)', 'Bash(git log:*)', 'Bash(git show:*)']


def command(base, head, comments, model):
    prompt = f'/context-packs:pack-review ci {base}...{head} {comments}'
    return ['claude', '-p', prompt, '--bare', '--restricted', '--plugin-dir', str(PLUGIN), '--add-dir', str(comments.parent),
            '--output-format', 'json', '--json-schema', SCHEMA.read_text(encoding='utf-8'),
            '--tools', ','.join(TOOLS), '--allowedTools', ','.join(ALLOWED), '--permission-prompts', 'none',
            '--strict-mcp-config', '--no-session-persistence', *(['--model', model] if model else [])]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', required=True, help='the commit the change starts from')
    parser.add_argument('--head', required=True, help='the commit to review')
    parser.add_argument('--comments', type=Path, required=True, help="the PR's comments, as fetch.py writes them")
    parser.add_argument('--out', type=Path, required=True, help='where to write the findings')
    parser.add_argument('--model', help="the model to review with, if not Claude Code's default")
    args = parser.parse_args()
    run = subprocess.run(command(args.base, args.head, args.comments.resolve(), args.model), capture_output=True,
                         text=True)
    if run.returncode != 0 and not run.stdout.strip():
        sys.exit(f'pack-review: claude exited with code {run.returncode} without a result:\n{run.stderr.strip()}')
    result = json.loads(run.stdout)
    if result.get('is_error'):
        sys.exit(f'pack-review: the review failed ({result["subtype"]}): {result.get("result", "")}')
    if not isinstance(result.get('structured_output'), dict):
        sys.exit(f'pack-review: the review returned no findings object. It said: {result.get("result", "")}')
    found = {'base': args.base, 'head': args.head, **result['structured_output']}
    args.out.write_text(json.dumps(found, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f'pack-review: {len(found["findings"])} findings, {len(found["threads"])} thread actions, '
          f'costing ${result.get("total_cost_usd", 0):.2f}.')


main()
