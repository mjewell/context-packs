#!/usr/bin/env python3
"""Write the merge job's report for the post job: the findings the merging agent returned, cleaned, and which docs
and which changed paths' diffs no agent read in full, from each finder's record and the merging agent's transcript. It
reaches nothing outside the runner, so the transcript, which can hold file contents, never leaves the job."""
import argparse
import json
import os
from pathlib import Path
import sys

import reads
from sanitize import clean
import units


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


def changed_in(changed):
    """The (lines, path) pairs the git server's changed tool lists."""
    pairs = []
    for line in changed.read_text(encoding='utf-8').splitlines():
        lines, path = line.split('\t', 1)
        pairs.append((int(lines), path))
    return pairs


def unread(found, what):
    """The paths no one read in full, after printing who read each one in the run's log."""
    for path, who in found.items():
        print(f'{what}read by {", ".join(who)}: {path}' if who else f'{what}not read: {path}')
    return cleaned([path for path, who in found.items() if not who])


def records_in(folder, count):
    """Each finder's record, from unit_report.py, in unit order. A missing one stops the run, since its unit's docs
    would otherwise count as unread with no word on why."""
    records = []
    for n in range(count):
        path = folder / f'unit-{n}.json'
        if not path.is_file():
            sys.exit(f"pack-review: there's no record from unit {n}'s finder, at {path}.")
        records.append(json.loads(path.read_text(encoding='utf-8')))
    return records


def merged(records, key, merger):
    """Who read each path in full, across every finder's record and the merging agent."""
    found = {}
    for record in records:
        for path, who in record[key].items():
            found.setdefault(path, []).extend(who)
    for path, who in merger.items():
        found.setdefault(path, []).extend(who)
    return found


def anchors(findings, shown):
    """The spot each finding's thread can open on: its first spot that deviates and the diff shows, or else its first
    spot the diff shows, or None when the diff shows none, since a review comment needs a line in the diff."""
    found = []
    for finding in findings:
        spots = [spot for spot in finding['spots'] if spot['line'] in shown.get(spot['path'], [])]
        spots.sort(key=lambda spot: spot['follows'])
        found.append({'path': spots[0]['path'], 'line': spots[0]['line']} if spots else None)
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', required=True, help='the commit the reviewed change starts from')
    parser.add_argument('--base-ref', required=True, help='the branch the PR was to merge into when it was reviewed')
    parser.add_argument('--head', required=True, help='the commit that was reviewed')
    parser.add_argument('--findings', type=Path, required=True, help="the merging agent's structured output")
    parser.add_argument('--transcript', type=Path, required=True,
                        help="the merging agent's claude-execution-output.json, from claude-code-action")
    parser.add_argument('--docs', type=Path, required=True,
                        help='the docs the finders should read, from the checkout, as `context-packs docs` prints them')
    parser.add_argument('--changed', type=Path, required=True,
                        help="the paths the change touches, as the git server's changed tool lists them")
    parser.add_argument('--shown', type=Path, required=True,
                        help='the head lines each diff shows, as `git_server.py shown` prints them')
    parser.add_argument('--units', type=Path, required=True, help="the folder holding each finder's unit-<n>.json")
    parser.add_argument('--out', type=Path, required=True, help='where to write the report')
    args = parser.parse_args()
    findings = findings_in(args.findings)
    paths = [path for unit in units.units(args.docs) for path in unit]
    records = records_in(args.units, len(units.units(args.docs)))
    messages = json.loads(args.transcript.read_text(encoding='utf-8'))
    changed = changed_in(args.changed)
    docs = merged(records, 'docs', reads.readers(messages, paths, os.path.realpath('.'), 'the merging agent'))
    diffs = merged(records, 'diffs', reads.diff_readers(messages, changed, 'the merging agent'))
    report = {'base': args.base, 'base_ref': args.base_ref, 'head': args.head, 'findings': findings,
              'anchors': anchors(findings, json.loads(args.shown.read_text(encoding='utf-8'))),
              'unread': unread({path: docs.get(path, []) for path in paths}, ''),
              'unread_diffs': unread({path: diffs.get(path, []) for _, path in changed}, 'diff ')}
    args.out.write_text(json.dumps(report, ensure_ascii=False), encoding='utf-8')


if __name__ == '__main__':
    main()
