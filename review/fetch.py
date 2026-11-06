#!/usr/bin/env python3
"""Write what the review agent reads about a PR besides its diff: its description, the comments and reviews of
people with a trusted role on the repo, and the review threads, marking the ones pack-review started. pack-review's
own summary is left out, and so is everything from anyone else, so text planted in the PR never reaches the agent."""
import argparse
import json
from pathlib import Path

import github


def text(comment):
    """The comment's body, without the marker ending pack-review's own."""
    body = comment['body'].rstrip()
    return body[:-len(github.MARKER)].rstrip() if github.own(comment) else body


def author(comment):
    return 'pack-review' if github.own(comment) else comment['author']['login']


def thread(raw):
    """The thread with only the comments the agent may read, or None if it has none."""
    comments = [{'author': author(c), 'body': text(c), 'pack_review': github.own(c)}
                for c in raw['comments'] if github.own(c) or github.trusted(c)]
    if not comments:
        return None
    return {'id': raw['id'], 'path': raw['path'], 'line': raw['line'], 'resolved': raw['isResolved'],
            'outdated': raw['isOutdated'], 'pack_review': github.own(raw['comments'][0]), 'comments': comments}


def comments(number):
    pr = github.pull_request(number)
    threads = [thread(raw) for raw in pr['reviewThreads']]
    return {
        'pull_request': {'number': number, 'title': pr['title'], 'body': pr['body'] if github.trusted(pr) else None,
                         'author': pr['author']['login']},
        'comments': [{'author': author(c), 'body': text(c)}
                     for c in pr['comments'] if github.trusted(c) and not github.own(c)],
        'reviews': [{'author': author(r), 'state': r['state'], 'body': text(r)}
                    for r in pr['reviews'] if github.trusted(r) and not github.own(r) and r['body'].strip()],
        'threads': [t for t in threads if t],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pr', type=int, required=True, help='the PR number')
    parser.add_argument('--out', type=Path, required=True, help='where to write the JSON')
    args = parser.parse_args()
    found = comments(args.pr)
    args.out.write_text(json.dumps(found, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


main()
