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
# The finding kinds, in the order the summary counts them. Each is a noun that takes an s for more than one.
KINDS = json.loads((Path(__file__).resolve().parent / 'findings.schema.json').read_text(encoding='utf-8'))[
    'properties']['findings']['items']['properties']['kind']['enum']
ADD_COMMENT = '''mutation AddComment($input: AddCommentInput!) { addComment(input: $input) { clientMutationId } }'''
UPDATE_COMMENT = '''mutation UpdateComment($input: UpdateIssueCommentInput!) {
  updateIssueComment(input: $input) { clientMutationId } }'''


def counted(findings):
    counts = {kind: sum(f['kind'] == kind for f in findings) for kind in KINDS}
    return ', '.join(f"{n} {kind}{'s' * (n != 1)}" for kind, n in counts.items() if n)


def summary(repo, number, report):
    """The counts for people, and the whole report as JSON. The agent's text appears only in the JSON, where nothing
    renders, so nothing they hold can show people something other than what the author's local
    run reads."""
    findings = report['findings']
    found = counted(findings) or 'nothing'
    text = f"pack-review checked `{report['head'][:7]}` against this repo's context packs and found {found}."
    if findings:
        text += f"\n\nTo go through them, run `/pack-review {repo}#{number}`."
    # Backticks and < only occur inside JSON strings, where \u0060 and \u003c mean the same. So nothing can close the
    # fence, and the block's title, which the local run counts, appears nowhere else.
    data = json.dumps({key: report[key] for key in ('base', 'base_ref', 'head', 'findings')},
                      indent=2, ensure_ascii=False)
    data = data.replace('`', '\\u0060').replace('<', '\\u003c')
    return github.signed(f'{text}\n\n<details><summary>Findings for pack-review</summary>\n\n```json\n{data}\n'
                         '```\n\n</details>')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pr', type=int, required=True, help='the PR number')
    parser.add_argument('--report', type=Path, required=True, help="the find job's report, from report.py")
    parser.add_argument('--paired', type=Path, required=True,
                        help="the threads job's pairs and commentary, from pairing.py")
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding='utf-8'))
    paired = json.loads(args.paired.read_text(encoding='utf-8'))
    threads = {pair['finding']: pair['thread'] for pair in paired['pairs']}
    commentary = {item['finding']: item['text'] for item in paired['commentary']}
    report['findings'] = [{**finding, 'thread': threads.get(n), 'commentary': commentary.get(n)}
                          for n, finding in enumerate(report['findings'])]
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
