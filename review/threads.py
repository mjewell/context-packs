#!/usr/bin/env python3
"""Print pack-review's review threads on a PR as JSON, with each comment as trust.py lets an agent see it. The threads
job runs it, and its agents read the threads from this output, so they need no tools."""
import argparse
import json
import sys

import github
import trust


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pr', type=int, required=True, help='the PR number, in the repo GITHUB_REPOSITORY names')
    args = parser.parse_args()
    print(json.dumps(trust.threads(args.pr), ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except github.GitHubError as error:
        sys.exit(f'pack-review: {error}')
