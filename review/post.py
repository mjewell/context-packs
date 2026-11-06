#!/usr/bin/env python3
"""Post a review's findings to its PR: carry out the agent's thread actions, then post or update pack-review's one
summary comment, which holds every finding for the author's local run. Everything is checked before anything is
written, and the agent can act only on threads pack-review started."""
import argparse
import base64
import json
from pathlib import Path
import sys

import github

# GitHub's limit on a comment's length.
LIMIT = 65536
NEEDS = {'new': ['path', 'line'], 'reply': ['thread'], 'resolve': ['thread']}
NAMES = {'deviates': ('deviation', 'deviations'), 'conflicting': ('conflict', 'conflicts'),
         'uncovered': ('uncovered choice', 'uncovered choices')}

ADD_REVIEW = '''mutation AddReview($input: AddPullRequestReviewInput!) {
  addPullRequestReview(input: $input) { clientMutationId } }'''
ADD_REPLY = '''mutation AddReply($input: AddPullRequestReviewThreadReplyInput!) {
  addPullRequestReviewThreadReply(input: $input) { clientMutationId } }'''
RESOLVE = '''mutation Resolve($input: ResolveReviewThreadInput!) {
  resolveReviewThread(input: $input) { clientMutationId } }'''
ADD_COMMENT = '''mutation AddComment($input: AddCommentInput!) { addComment(input: $input) { clientMutationId } }'''
UPDATE_COMMENT = '''mutation UpdateComment($input: UpdateIssueCommentInput!) {
  updateIssueComment(input: $input) { clientMutationId } }'''


def signed(body):
    """A comment as pack-review posts it: marked as Claude's for people, and as pack-review's for the next run."""
    return f'🤖 {body.strip()}\n\n{github.MARKER}'


def check(actions, pr):
    """Stop, before anything is written, on an action missing what it needs or aimed at a thread pack-review didn't
    start."""
    started = {t['id'] for t in pr['reviewThreads'] if github.own(t['comments'][0])}
    for action in actions:
        for field in NEEDS[action['action']]:
            if field not in action:
                sys.exit(f'pack-review: a {action["action"]} action needs a {field}: {json.dumps(action)}')
        if 'thread' in NEEDS[action['action']] and action['thread'] not in started:
            sys.exit(f'pack-review: {action["thread"]} is not a thread pack-review started, so it won\'t '
                     f'{action["action"]} it.')


def counted(findings):
    counts = {kind: sum(f['kind'] == kind for f in findings) for kind in NAMES}
    return ', '.join(f'{n} {NAMES[kind][n != 1]}' for kind, n in counts.items() if n)


def summary(review, number):
    findings = review['findings']
    shown = [f for f in findings if f['inline']]
    held = [f for f in findings if not f['inline']]
    checked = f'pack-review checked `{review["head"][:7]}` against this repo\'s context packs'
    if not findings:
        text = f'{checked} and found nothing.'
    else:
        lines = [f'- Commented on the diff: {counted(shown)}.'] * bool(shown)
        lines += [f"- For the author's local review only: {counted(held)}."] * bool(held)
        text = (f'{checked}.\n\n' + '\n'.join(lines) + '\n\nTo go through them all, run '
                f'`/pack-review {number}` in Claude Code with this PR\'s branch checked out.')
    data = {key: review[key] for key in ('base', 'head', 'findings')}
    encoded = base64.encodebytes(json.dumps(data, ensure_ascii=False).encode()).decode().strip()
    return signed(f'{text}\n\n<!-- pack-review:findings\n{encoded}\n-->')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pr', type=int, required=True, help='the PR number')
    parser.add_argument('--findings', type=Path, required=True, help='the findings, as gather.py writes them')
    args = parser.parse_args()
    review = json.loads(args.findings.read_text(encoding='utf-8'))
    pr = github.pull_request(args.pr)
    if pr['headRefOid'] != review['head']:
        print(f'pack-review: the PR moved on to {pr["headRefOid"]} since this review of {review["head"]}, so it '
              'posts nothing. The run for the newer commit will.')
        return
    actions = review['threads']
    check(actions, pr)
    body = summary(review, args.pr)
    if len(body) > LIMIT:
        sys.exit(f'pack-review: the summary is {len(body)} characters, and GitHub allows {LIMIT} in a comment.')
    summaries = [c['id'] for c in pr['comments'] if github.own(c)]
    if len(summaries) > 1:
        sys.exit(f'pack-review: the PR has more than one pack-review summary ({", ".join(summaries)}). Delete all '
                 'but one.')

    new = [{'path': a['path'], 'line': a['line'], 'side': 'RIGHT', 'body': signed(a['body'])}
           for a in actions if a['action'] == 'new']
    if new:
        # GitHub's docs require a body on a COMMENT review.
        opened = f'pack-review opened {len(new)} thread{"s" * (len(new) != 1)} on `{review["head"][:7]}`.'
        github.graphql('AddReview', ADD_REVIEW, {'input': {
            'pullRequestId': pr['id'], 'commitOID': review['head'], 'event': 'COMMENT', 'body': signed(opened),
            'threads': new}})
    for action in actions:
        if action['action'] in ('reply', 'resolve'):
            github.graphql('AddReply', ADD_REPLY, {'input': {'pullRequestReviewThreadId': action['thread'],
                                                             'body': signed(action['body'])}})
        if action['action'] == 'resolve':
            github.graphql('Resolve', RESOLVE, {'input': {'threadId': action['thread']}})
    if summaries:
        github.graphql('UpdateComment', UPDATE_COMMENT, {'input': {'id': summaries[0], 'body': body}})
    else:
        github.graphql('AddComment', ADD_COMMENT, {'input': {'subjectId': pr['id'], 'body': body}})
    print(f'pack-review: posted {len(new)} new threads, {len(actions) - len(new)} replies and resolutions, and the '
          'summary.')


main()
