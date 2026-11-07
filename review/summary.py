#!/usr/bin/env python3
"""Post or update pack-review's one summary comment on a PR, from the findings the review agent returned: counts for
people, and every finding as JSON for the author's local run. It runs as a step after the agent, which can't write to
the PR."""
import argparse
import json
import os
from pathlib import Path
import sys

import github
from sanitize import clean

# GitHub's limit on a comment's length.
LIMIT = 65536
NAMES = {'deviates': ('deviation', 'deviations'), 'conflicting': ('conflict', 'conflicts'),
         'uncovered': ('uncovered choice', 'uncovered choices')}
ADD_COMMENT = '''mutation AddComment($input: AddCommentInput!) { addComment(input: $input) { clientMutationId } }'''
UPDATE_COMMENT = '''mutation UpdateComment($input: UpdateIssueCommentInput!) {
  updateIssueComment(input: $input) { clientMutationId } }'''


def cleaned(value):
    """The agent's findings with every string cleaned of what a reader wouldn't see."""
    if isinstance(value, str):
        return clean(value)
    if isinstance(value, list):
        return [cleaned(item) for item in value]
    if isinstance(value, dict):
        return {key: cleaned(item) for key, item in value.items()}
    return value


def counted(findings):
    counts = {kind: sum(f['kind'] == kind for f in findings) for kind in NAMES}
    return ', '.join(f'{n} {NAMES[kind][n != 1]}' for kind, n in counts.items() if n)


def summary(repo, number, base, head, findings):
    """The counts for people, and every finding as JSON. The agent's text appears only in the JSON, where nothing
    renders, so nothing it writes can show people something other than what the author's local run reads."""
    found = counted(findings) or 'nothing'
    text = f"pack-review checked `{head[:7]}` against this repo's context packs and found {found}."
    if findings:
        text += (f"\n\nTo go through them, run `/pack-review {repo}#{number}` in Claude Code with this PR's branch "
                 'checked out.')
    # Backticks only occur inside JSON strings, where \u0060 means the same, so nothing can close the fence.
    data = json.dumps({'base': base, 'head': head, 'findings': findings}, indent=2, ensure_ascii=False)
    data = data.replace('`', '\\u0060')
    return github.signed(f'{text}\n\n<details><summary>Findings for the local review</summary>\n\n```json\n{data}\n'
                         '```\n\n</details>')


def findings_in(path):
    try:
        output = json.loads(path.read_text(encoding='utf-8'))
    except ValueError:
        output = None
    if not isinstance(output, dict) or not isinstance(output.get('findings'), list):
        sys.exit(f'pack-review: the review returned no findings: {path.read_text(encoding="utf-8")[:500]!r}')
    return cleaned(output['findings'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pr', type=int, required=True, help='the PR number')
    parser.add_argument('--base', required=True, help='the commit the reviewed change starts from')
    parser.add_argument('--head', required=True, help='the commit that was reviewed')
    parser.add_argument('--findings', type=Path, required=True, help="the review agent's structured output")
    args = parser.parse_args()
    findings = findings_in(args.findings)
    pr = github.pull_request(args.pr)
    if pr['headRefOid'] != args.head:
        print(f'pack-review: the PR moved on to {pr["headRefOid"]} since this review of {args.head}, so it posts '
              'no summary. The run for the newer commit will.')
        return
    body = summary(os.environ['GITHUB_REPOSITORY'], args.pr, args.base, args.head, findings)
    if len(body) > LIMIT:
        sys.exit(f'pack-review: the summary is {len(body)} characters, and GitHub allows {LIMIT} in a comment.')
    summaries = [c['id'] for c in pr['comments'] if github.own(c)]
    if len(summaries) > 1:
        sys.exit(f'pack-review: the PR has more than one pack-review summary ({", ".join(summaries)}). Delete all '
                 'but one.')
    if summaries:
        github.graphql('UpdateComment', UPDATE_COMMENT, {'input': {'id': summaries[0], 'body': body}})
    else:
        github.graphql('AddComment', ADD_COMMENT, {'input': {'subjectId': pr['id'], 'body': body}})
    print(f'pack-review: posted the summary of {len(findings)} findings.')


if __name__ == '__main__':
    try:
        main()
    except github.GitHubError as error:
        sys.exit(f'pack-review: {error}')
