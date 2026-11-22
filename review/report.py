#!/usr/bin/env python3
"""Write the merge job's report for the pairing and post jobs: the findings, built from the finders' findings each of
the merging agent's groups names, cleaned, and the line each one's thread can open on. It reaches nothing outside the
runner."""
import argparse
import json
from pathlib import Path
import sys

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


def groups_in(path):
    try:
        output = json.loads(path.read_text(encoding='utf-8'))
    except ValueError:
        output = None
    if not isinstance(output, dict) or not isinstance(output.get('groups'), list):
        sys.exit(f'pack-review: the merge returned no groups: {path.read_text(encoding="utf-8")[:500]!r}')
    return output['groups']


def unique(items):
    """The items in order, each once."""
    return [item for n, item in enumerate(items) if item not in items[:n]]


def built(group, sources):
    """The finding a group makes: its kind, headline and take, and every rule, spot, sign and exemplar of the finders'
    findings it names. A spot two of them disagree on deviates, since it goes against at least one rule."""
    found = [sources[id] for id in group['ids']]
    spots = {}
    for spot in (spot for finding in found for spot in finding['spots']):
        key = (spot['path'], spot['line'])
        spots[key] = {**spot, 'follows': spots[key]['follows'] and spot['follows']} if key in spots else spot
    return {'kind': group['kind'], 'headline': group['headline'],
            'rules': unique([rule for finding in found for rule in finding['rules']]), 'spots': list(spots.values()),
            'deliberate': unique([sign for finding in found for sign in finding['deliberate']]),
            'exemplars': unique([way for finding in found for way in finding['exemplars']]), 'take': group['take']}


def checked(groups, sources):
    """The groups, when they name every finder's finding exactly once and no other. A finding left out or named twice
    would drop or repeat what a finder found without anything failing."""
    named = [id for group in groups for id in group['ids']]
    invented = unique([id for id in named if id not in sources])
    if invented:
        sys.exit(f"pack-review: the merge's groups name {', '.join(invented)}, which no finder reported.")
    repeated = unique([id for n, id in enumerate(named) if id in named[:n]])
    if repeated:
        sys.exit(f"pack-review: the merge's groups put {', '.join(repeated)} in more than one group.")
    left = [id for id in sources if id not in named]
    if left:
        sys.exit(f"pack-review: the merge's groups leave out {', '.join(left)}.")
    return groups


def findings_in(groups_path, sources_path):
    sources = {source['id']: source['finding'] for source in json.loads(sources_path.read_text(encoding='utf-8'))}
    return cleaned([built(group, sources) for group in checked(groups_in(groups_path), sources)])


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
    parser.add_argument('--sources', type=Path, required=True,
                        help="the finders' findings, as `units.py merge` numbers them")
    parser.add_argument('--groups', type=Path, required=True, help="the merging agent's structured output")
    parser.add_argument('--shown', type=Path, required=True,
                        help='the head lines each diff shows, as `git_server.py shown` prints them')
    parser.add_argument('--out', type=Path, required=True, help='where to write the report')
    args = parser.parse_args()
    findings = findings_in(args.groups, args.sources)
    report = {'base': args.base, 'base_ref': args.base_ref, 'head': args.head, 'findings': findings,
              'anchors': anchors(findings, json.loads(args.shown.read_text(encoding='utf-8')))}
    args.out.write_text(json.dumps(report, ensure_ascii=False), encoding='utf-8')


if __name__ == '__main__':
    main()
