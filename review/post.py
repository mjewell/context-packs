#!/usr/bin/env python3
"""Post the review's threads as one GitHub review: a new thread for each finding no thread was opened for, and a reply
in a pack-review thread only when there's something to say. It runs in the post job, which has no agent. It reads
pack-review's threads afresh through trust.py, so it writes only to threads pack-review opened on this PR."""
import argparse
import json
from pathlib import Path
import sys

import finding_comment
import github
import trust

PR_HEAD = '''query PullRequestHead($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) { pullRequest(number: $number) { id headRefOid baseRefName } } }'''
ADD_REVIEW = '''mutation AddReview($input: AddPullRequestReviewInput!) {
  addPullRequestReview(input: $input) { pullRequestReview { id } } }'''
ADD_REPLY = '''mutation AddReply($input: AddPullRequestReviewThreadReplyInput!) {
  addPullRequestReviewThreadReply(input: $input) { comment { id } } }'''
SUBMIT_REVIEW = '''mutation SubmitReview($input: SubmitPullRequestReviewInput!) {
  submitPullRequestReview(input: $input) { pullRequestReview { id } } }'''


def reply(head, resolved, commentary):
    """The reply in a thread whose finding the review still finds, or None when it has nothing to say."""
    if commentary is None:
        return github.signed(f'The review still finds this at `{head[:7]}`.') if resolved else None
    lead = f'The review still finds this at `{head[:7]}`.' if resolved else f'At `{head[:7]}`:'
    return github.signed(f'{lead}\n\n{finding_comment.quoted(commentary)}')


def planned(report, matched, threads):
    """The new threads and the replies, by thread id, that the review posts."""
    head, findings = report['head'], report['findings']
    pairs = {pair['finding']: pair['thread'] for pair in matched['pairs']}
    commentary = {item['finding']: item['text'] for item in matched['commentary']}
    for thread in pairs.values():
        if thread not in threads:
            sys.exit(f"pack-review: the pairs name {thread}, which isn't one of pack-review's threads on this PR.")
    new, replies = [], {}
    for n, finding in enumerate(findings):
        anchor = report['anchors'][n]
        if n not in pairs:
            if anchor is not None:
                new.append({'path': anchor['path'], 'line': anchor['line'], 'side': 'RIGHT',
                            'body': finding_comment.body(finding, head)})
            continue
        thread = pairs[n]
        body = reply(head, threads[thread]['resolved'], commentary.get(n))
        if body is not None:
            replies[thread] = body
    return new, replies


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pr', type=int, required=True, help='the PR number')
    parser.add_argument('--report', type=Path, required=True, help="the find job's report, from report.py")
    parser.add_argument('--match', type=Path, required=True, help="the match job's pairs and commentary")
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding='utf-8'))
    matched = json.loads(args.match.read_text(encoding='utf-8'))
    owner, name = github.repository()
    pr = github.graphql('PullRequestHead', PR_HEAD, {'owner': owner, 'name': name, 'number': args.pr})
    pr = pr['repository']['pullRequest']
    if pr['headRefOid'] != report['head']:
        print(f'pack-review: the PR moved on to {pr["headRefOid"]} since this review of {report["head"]}, so it posts '
              'no threads. The run for the newer commit will.')
        return
    if pr['baseRefName'] != report['base_ref']:
        print(f'pack-review: the PR moved from {report["base_ref"]} to {pr["baseRefName"]} since this review, so it '
              'posts no threads. The run for the new base will.')
        return
    threads = {thread['id']: thread for thread in trust.threads(args.pr)}
    new, replies = planned(report, matched, threads)
    if not new and not replies:
        print('pack-review: nothing to post in threads.')
        return
    # A review with no event stays pending, so the replies join it and everything appears at once when it's submitted.
    review = github.graphql('AddReview', ADD_REVIEW, {'input': {
        'pullRequestId': pr['id'], 'commitOID': report['head'], 'threads': new}})
    review = review['addPullRequestReview']['pullRequestReview']['id']
    for thread, body in replies.items():
        github.graphql('AddReply', ADD_REPLY, {'input': {'pullRequestReviewId': review,
                                                         'pullRequestReviewThreadId': thread, 'body': body}})
    github.graphql('SubmitReview', SUBMIT_REVIEW, {'input': {'pullRequestReviewId': review, 'event': 'COMMENT'}})
    print(f'pack-review: opened {len(new)} threads and replied in {len(replies)}.')


if __name__ == '__main__':
    try:
        main()
    except github.GitHubError as error:
        sys.exit(f'pack-review: {error}')
