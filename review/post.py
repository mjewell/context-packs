#!/usr/bin/env python3
"""Post the review: a GitHub review that opens a thread for each finding no thread was opened for, a reply in a
pack-review thread only when there's something to say, then the one summary comment. No review is ever left pending:
the new threads are submitted as they're created and each reply is posted on its own, so a write that fails or a run
that's cancelled leaves only comments the next run can pick up from. It runs in the post job, which
has no agent. It plans every write and checks the plan before the first one, so a run that stops on a check leaves the
PR as it was. It reads pack-review's threads afresh through trust.py, so it writes only to threads pack-review opened
on this PR."""
import argparse
import json
import os
from pathlib import Path
import sys

import finding_comment
import github
import summary
import trust

ADD_REVIEW = '''mutation AddReview($input: AddPullRequestReviewInput!) {
  addPullRequestReview(input: $input) { pullRequestReview { id } } }'''
ADD_REPLY = '''mutation AddReply($input: AddPullRequestReviewThreadReplyInput!) {
  addPullRequestReviewThreadReply(input: $input) { comment { id } } }'''
ADD_COMMENT = '''mutation AddComment($input: AddCommentInput!) { addComment(input: $input) { clientMutationId } }'''
UPDATE_COMMENT = '''mutation UpdateComment($input: UpdateIssueCommentInput!) {
  updateIssueComment(input: $input) { clientMutationId } }'''


STILL_FOUND = 'still found'


def told(thread):
    """Whether pack-review's last word in the thread is already that its finding is still found. Its bodyText drops the
    code spans, so it reads "🤖 still found <sha>"."""
    last = thread['comments'][-1]
    return bool(last.get('ours')) and last['text'].startswith(f'🤖 {STILL_FOUND}')


def reply(head, resolved, commentary):
    """The reply in a thread whose finding the review still finds, or None when it has nothing to say. It leads with
    the commit as a tag, and `still found` before it when the thread was resolved."""
    lead = f'`{STILL_FOUND}` `{head[:7]}`' if resolved else f'`{head[:7]}`'
    if commentary is None:
        return github.signed(lead) if resolved else None
    return github.signed(f'{lead}\n\n{finding_comment.quoted(commentary)}')


def stale(report, pr):
    """Why the PR no longer matches what was reviewed, or None when it does."""
    if pr['headRefOid'] != report['head']:
        return (f'the PR moved on to {pr["headRefOid"]} since this review of {report["head"]}, so it posts nothing. '
                'The run for the newer commit will.')
    if pr['baseRefName'] != report['base_ref']:
        return (f'the PR moved from {report["base_ref"]} to {pr["baseRefName"]} since this review, so it posts '
                'nothing. The run for the new base will.')
    return None


def planned(repo, number, report, paired, pr, threads):
    """Every write the review makes: the new threads, the replies by thread id, and the summary's body with the id of
    the summary it replaces, or None when it adds one. It stops on anything that would fail partway through posting."""
    head, findings = report['head'], report['findings']
    pairs = {pair['finding']: pair['thread'] for pair in paired['pairs']}
    commentary = {item['finding']: item['text'] for item in paired['commentary']}
    for thread in pairs.values():
        if thread not in threads:
            sys.exit(f"pack-review: the pairs name {thread}, which isn't one of pack-review's threads on this PR.")
    new, replies = [], {}
    for n, finding in enumerate(findings):
        anchor = report['anchors'][n]
        if n not in pairs:
            if anchor is not None:
                new.append({'path': anchor['path'], 'line': anchor['line'], 'side': 'RIGHT',
                            'body': finding_comment.body(finding, head, anchor)})
            continue
        thread = pairs[n]
        # A resolved thread hears its finding is still found once, until someone comments after that.
        resolved = threads[thread]['resolved'] and not told(threads[thread])
        body = reply(head, resolved, commentary.get(n))
        if body is not None:
            replies[thread] = body
    body = summary.body(repo, number, {**report, 'findings': [
        {**finding, 'thread': pairs.get(n), 'commentary': commentary.get(n)} for n, finding in enumerate(findings)]})
    if len(body) > summary.LIMIT:
        sys.exit(f'pack-review: the summary is {len(body)} characters, and GitHub allows {summary.LIMIT} in a comment.')
    summaries = [c['id'] for c in pr['comments'] if github.own(c)]
    if len(summaries) > 1:
        sys.exit(f'pack-review: the PR has more than one pack-review summary ({", ".join(summaries)}). Delete all '
                 'but one.')
    return new, replies, (body, summaries[0] if summaries else None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pr', type=int, required=True, help='the PR number')
    parser.add_argument('--report', type=Path, required=True, help="the find job's report, from report.py")
    parser.add_argument('--paired', type=Path, required=True, help="the pairing job's pairs and commentary")
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding='utf-8'))
    paired = json.loads(args.paired.read_text(encoding='utf-8'))
    pr = github.pull_request(args.pr)
    why = stale(report, pr)
    if why:
        print(f'pack-review: {why}')
        return
    threads = {thread['id']: thread for thread in trust.threads(args.pr)}
    new, replies, (body, existing) = planned(os.environ['GITHUB_REPOSITORY'], args.pr, report, paired, pr, threads)
    if new:
        github.graphql('AddReview', ADD_REVIEW, {'input': {
            'pullRequestId': pr['id'], 'commitOID': report['head'], 'event': 'COMMENT', 'threads': new}})
    for thread, text in replies.items():
        # A reply joins a review only while that review is pending, so each one is posted on its own.
        try:
            github.graphql('AddReply', ADD_REPLY, {'input': {'pullRequestReviewThreadId': thread, 'body': text}})
        except github.GitHubError as error:
            sys.exit(f'pack-review: in thread {thread}: {error}')
    if existing:
        github.graphql('UpdateComment', UPDATE_COMMENT, {'input': {'id': existing, 'body': body}})
    else:
        github.graphql('AddComment', ADD_COMMENT, {'input': {'subjectId': pr['id'], 'body': body}})
    print(f'pack-review: opened {len(new)} threads, replied in {len(replies)}, and posted the summary of '
          f'{len(report["findings"])} findings.')


if __name__ == '__main__':
    try:
        main()
    except github.GitHubError as error:
        sys.exit(f'pack-review: {error}')
