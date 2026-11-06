#!/usr/bin/env python3
"""The review agent's tools for its PR, as an MCP server over stdin and stdout. read_comments gives it what people
trusted on the repo and pack-review itself wrote. open_thread and reply write to the PR, and reply only on threads
pack-review started. There's no tool to resolve a thread, since GitHub refuses that to the workflow's token.
Everything read and written is cleaned of what a reader of the PR wouldn't see, and everything written is marked as
pack-review's. The token comes from the environment, which the agent's tools can't read."""
import argparse
import json
import sys

import github
from sanitize import clean

STRING = {'type': 'string'}
THREAD = {'type': 'string', 'description': "The thread's id, from read_comments."}
TOOLS = [
    ('read_comments', "The PR's description, and the comments, reviews and review threads of people with a trusted "
                      'role on the repo. Threads and comments marked pack_review are yours from earlier runs.', {}),
    ('open_thread', 'Open a review thread on a line of the head commit, which must be in the diff. Write Markdown; '
                    'the 🤖 and the marker are added for you.',
     {'path': STRING, 'line': {'type': 'integer'}, 'body': STRING}),
    ('reply', 'Reply in a thread you started.', {'thread': THREAD, 'body': STRING}),
]
ADD_REPLY = '''mutation AddReply($input: AddPullRequestReviewThreadReplyInput!) {
  addPullRequestReviewThreadReply(input: $input) { clientMutationId } }'''


class Refused(Exception):
    """A call the agent may not make."""


def text(comment):
    return clean(comment['body'])


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


class Tools:
    def __init__(self, number, head):
        self.number = number
        self.head = head

    def read_comments(self):
        pr = github.pull_request(self.number)
        threads = [thread(raw) for raw in pr['reviewThreads']]
        return json.dumps({
            'pull_request': {'number': self.number, 'title': clean(pr['title']),
                             'body': text(pr) if github.trusted(pr) else None, 'author': pr['author']['login']},
            'comments': [{'author': author(c), 'body': text(c)}
                         for c in pr['comments'] if github.trusted(c) and not github.own(c)],
            'reviews': [{'author': author(r), 'state': r['state'], 'body': text(r)}
                        for r in pr['reviews'] if github.trusted(r) and not github.own(r) and r['body'].strip()],
            'threads': [t for t in threads if t],
        }, indent=2, ensure_ascii=False)

    def open_thread(self, path, line, body):
        posted = github.post(f'pulls/{self.number}/comments', {
            'commit_id': self.head, 'path': path, 'line': line, 'side': 'RIGHT', 'body': github.signed(clean(body))})
        return f'Opened a thread: {posted["html_url"]}'

    def check(self, id):
        if id not in github.started(github.pull_request(self.number)):
            raise Refused(f'{id} is not a thread pack-review started, so you may not write to it.')

    def reply(self, thread, body):
        self.check(thread)
        github.graphql('AddReply', ADD_REPLY, {'input': {'pullRequestReviewThreadId': thread,
                                                         'body': github.signed(clean(body))}})
        return f'Replied in {thread}.'


def listed():
    return [{'name': name, 'description': description,
             'inputSchema': {'type': 'object', 'properties': properties, 'required': list(properties),
                             'additionalProperties': False}}
            for name, description, properties in TOOLS]


def call(tools, name, arguments):
    """The tool's result. A refusal, from GitHub or from the checks here, goes back to the agent as an error it can
    act on."""
    known = {tool: properties for tool, _, properties in TOOLS}
    try:
        if name not in known:
            raise Refused(f'There is no tool named {name}.')
        missing = [field for field in known[name] if field not in arguments]
        if missing:
            raise Refused(f'{name} needs {", ".join(missing)}.')
        result, error = getattr(tools, name)(**{field: arguments[field] for field in known[name]}), False
    except (Refused, github.GitHubError) as refusal:
        result, error = str(refusal), True
    return {'content': [{'type': 'text', 'text': result}], 'isError': error}


def answer(tools, message):
    """The response to a request, or None for a notification."""
    if 'id' not in message:
        return None
    method, params = message['method'], message.get('params', {})
    if method == 'initialize':
        result = {'protocolVersion': params['protocolVersion'], 'capabilities': {'tools': {}},
                  'serverInfo': {'name': 'pack-review', 'version': '1'}}
    elif method == 'tools/list':
        result = {'tools': listed()}
    elif method == 'tools/call':
        result = call(tools, params['name'], params.get('arguments', {}))
    elif method == 'ping':
        result = {}
    else:
        return {'jsonrpc': '2.0', 'id': message['id'], 'error': {'code': -32601, 'message': f'No method {method}.'}}
    return {'jsonrpc': '2.0', 'id': message['id'], 'result': result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pr', type=int, required=True, help='the PR number')
    parser.add_argument('--head', required=True, help='the commit under review, which new threads comment on')
    args = parser.parse_args()
    tools = Tools(args.pr, args.head)
    sys.stdin.reconfigure(encoding='utf-8')
    for line in sys.stdin:
        response = answer(tools, json.loads(line))
        if response:
            sys.stdout.write(json.dumps(response) + '\n')
            sys.stdout.flush()


if __name__ == '__main__':
    main()
