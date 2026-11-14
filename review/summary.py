#!/usr/bin/env python3
"""Post or update pack-review's one summary comment on a PR, from the find job's report: counts for people, and every
finding as JSON for the author's local run, with any docs and diffs the agent didn't read. It runs in the post job,
which has no agent, so the only text it posts from the agent is what the report holds."""
import argparse
import json
import os
from pathlib import Path
import sys

import github

# GitHub's limit on a comment's length.
LIMIT = 65536
NAMES = {'deviates': ('deviation', 'deviations'), 'conflicting': ('conflict', 'conflicts'),
         'uncovered': ('uncovered choice', 'uncovered choices')}
ADD_COMMENT = '''mutation AddComment($input: AddCommentInput!) { addComment(input: $input) { clientMutationId } }'''
UPDATE_COMMENT = '''mutation UpdateComment($input: UpdateIssueCommentInput!) {
  updateIssueComment(input: $input) { clientMutationId } }'''


def counted(findings):
    counts = {kind: sum(f['kind'] == kind for f in findings) for kind in NAMES}
    return ', '.join(f'{n} {NAMES[kind][n != 1]}' for kind, n in counts.items() if n)


def summary(repo, number, report):
    """The counts for people, and the whole report as JSON. The agent's text and the docs' paths appear only in the
    JSON, where nothing renders, so nothing they hold can show people something other than what the author's local
    run reads."""
    findings, unread = report['findings'], report['unread']
    found = counted(findings) or 'nothing'
    text = f"pack-review checked `{report['head'][:7]}` against this repo's context packs and found {found}."
    if unread:
        text += (f' The review should read every doc the tables point at, and it skipped {len(unread)}. That\'s most '
                 'likely a problem in the review action, not in your docs. The JSON lists them.')
    if findings or unread:
        text += (f"\n\nTo go through them, run `/pack-review {repo}#{number}` in Claude Code with this PR's branch "
                 'checked out.')
    # Backticks only occur inside JSON strings, where \u0060 means the same, so nothing can close the fence.
    data = json.dumps({key: report[key] for key in ('base', 'base_ref', 'head', 'findings', 'unread', 'unread_diffs')},
                      indent=2, ensure_ascii=False)
    data = data.replace('`', '\\u0060')
    return github.signed(f'{text}\n\n<details><summary>Findings for the local review</summary>\n\n```json\n{data}\n'
                         '```\n\n</details>')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pr', type=int, required=True, help='the PR number')
    parser.add_argument('--report', type=Path, required=True, help="the find job's report, from report.py")
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding='utf-8'))
    pr = github.pull_request(args.pr)
    if pr['headRefOid'] != report['head']:
        print(f'pack-review: the PR moved on to {pr["headRefOid"]} since this review of {report["head"]}, so it posts '
              'no summary. The run for the newer commit will.')
        return
    if pr['baseRefName'] != report['base_ref']:
        print(f'pack-review: the PR moved from {report["base_ref"]} to {pr["baseRefName"]} since this review, so it posts '
              'no summary. The run for the new base will.')
        return
    body = summary(os.environ['GITHUB_REPOSITORY'], args.pr, report)
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
    print(f'pack-review: posted the summary of {len(report["findings"])} findings.')


if __name__ == '__main__':
    try:
        main()
    except github.GitHubError as error:
        sys.exit(f'pack-review: {error}')
