#!/usr/bin/env python3
"""Write the find job's report for the post job: the findings the review agent returned, cleaned, and which docs and
which changed paths' diffs no agent read, from the transcript. It runs in the find job after the agent, and reaches
nothing outside the runner, so the transcript, which can hold file contents, never leaves the job."""
import argparse
import json
import os
from pathlib import Path
import sys

import reads
from sanitize import clean


def cleaned(value):
    """The agent's findings with invisible characters removed and secrets redacted from every string."""
    if isinstance(value, str):
        return clean(value)
    if isinstance(value, list):
        return [cleaned(item) for item in value]
    if isinstance(value, dict):
        return {key: cleaned(item) for key, item in value.items()}
    return value


def findings_in(path):
    try:
        output = json.loads(path.read_text(encoding='utf-8'))
    except ValueError:
        output = None
    if not isinstance(output, dict) or not isinstance(output.get('findings'), list):
        sys.exit(f'pack-review: the review returned no findings: {path.read_text(encoding="utf-8")[:500]!r}')
    return cleaned(output['findings'])


def unread_in(transcript, docs):
    """The docs no agent read in full, after printing who read each one in the run's log."""
    listed = [doc for doc in docs.read_text(encoding='utf-8').splitlines() if doc]
    found = reads.readers(json.loads(transcript.read_text(encoding='utf-8')), listed, os.path.realpath('.'))
    for doc, who in found.items():
        print(f'read by {", ".join(who)}: {doc}' if who else f'not read: {doc}')
    return cleaned([doc for doc, who in found.items() if not who])


def unread_diffs_in(transcript, changed):
    """The changed paths whose diff no agent read in full, after printing who read each one in the run's log. Skipping
    a lock file is often right, so these don't make the review partial."""
    pairs = []
    for line in changed.read_text(encoding='utf-8').splitlines():
        lines, path = line.split('\t', 1)
        pairs.append((int(lines), path))
    found = reads.diff_readers(json.loads(transcript.read_text(encoding='utf-8')), pairs)
    for path, who in found.items():
        print(f'diff read by {", ".join(who)}: {path}' if who else f'diff not read: {path}')
    return cleaned([path for path, who in found.items() if not who])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', required=True, help='the commit the reviewed change starts from')
    parser.add_argument('--base-ref', required=True, help='the branch the PR was to merge into when it was reviewed')
    parser.add_argument('--head', required=True, help='the commit that was reviewed')
    parser.add_argument('--findings', type=Path, required=True, help="the review agent's structured output")
    parser.add_argument('--transcript', type=Path, required=True,
                        help="claude-code-action's claude-execution-output.json, to tell which docs the agent read")
    parser.add_argument('--docs', type=Path, required=True,
                        help='the docs the agent should read, from the checkout, as `context-packs docs` prints them')
    parser.add_argument('--changed', type=Path, required=True,
                        help="the paths the change touches, as the git server's changed tool lists them")
    parser.add_argument('--out', type=Path, required=True, help='where to write the report')
    args = parser.parse_args()
    report = {'base': args.base, 'base_ref': args.base_ref, 'head': args.head, 'findings': findings_in(args.findings),
              'unread': unread_in(args.transcript, args.docs),
              'unread_diffs': unread_diffs_in(args.transcript, args.changed)}
    args.out.write_text(json.dumps(report, ensure_ascii=False), encoding='utf-8')


if __name__ == '__main__':
    main()
