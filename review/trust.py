"""What of a PR's review threads an agent may read. A comment's text comes back only when its author can write to the
repo now, or pack-review wrote it. Anyone else's comment comes back as its id and why it's hidden, without their login,
which is text they chose. The threads job reads threads only through this module, so the rule has one home."""
import urllib.parse

import github
from sanitize import clean

PAGE = 100
FIELDS = 'id author { login __typename } createdAt body bodyText viewerDidAuthor isMinimized'
LIST = f'pageInfo {{ hasNextPage endCursor }} nodes {{ {FIELDS} }}'
THREADS = f'''query Threads($owner: String!, $name: String!, $number: Int!, $after: String) {{
  repository(owner: $owner, name: $name) {{ pullRequest(number: $number) {{
    reviewThreads(first: {PAGE}, after: $after) {{ pageInfo {{ hasNextPage endCursor }}
      nodes {{ id path line isResolved comments(first: {PAGE}) {{ {LIST} }} }} }} }} }} }}'''
THREAD_COMMENTS = f'''query ThreadComments($id: ID!, $after: String) {{
  node(id: $id) {{ ... on PullRequestReviewThread {{ comments(first: {PAGE}, after: $after) {{ {LIST} }} }} }} }}'''
# GitHub's roles that can push.
WRITERS = {'write', 'maintain', 'admin'}


def every(operation, query, variables, field, after=None):
    """Every item of a list from after on, reading each page in turn. field finds the list in an answer."""
    items = []
    while True:
        page = field(github.graphql(operation, query, {**variables, 'after': after}))
        items += page['nodes']
        if not page['pageInfo']['hasNextPage']:
            return items
        after = page['pageInfo']['endCursor']


def own(node):
    """Whether pack-review wrote it: the token's identity wrote it, and it ends with the marker."""
    return node['viewerDidAuthor'] and node['body'].rstrip().endswith(github.MARKER)


class Access:
    """Who can write to the repo now, asked of GitHub once per author."""

    def __init__(self, owner, name):
        self.owner, self.name = owner, name
        self.known = {}

    def writes(self, login):
        if login not in self.known:
            try:
                answer = github.rest(f'/repos/{self.owner}/{self.name}/collaborators/'
                                     f'{urllib.parse.quote(login, safe="")}/permission')
                self.known[login] = answer.get('role_name') in WRITERS
            except github.GitHubError as error:
                # GitHub answers 404 for someone who isn't a collaborator. Any other refusal stops the run.
                if error.code != 404:
                    raise
                self.known[login] = False
        return self.known[login]


def shown(node, access):
    """The comment as the agent may see it."""
    author = node['author']
    if node['isMinimized']:
        why = 'minimized'
    elif own(node):
        why = None
    elif author is not None and author['__typename'] == 'Bot':
        why = 'written by a bot'
    elif author is None or not access.writes(author['login']):
        why = 'author lacks write access'
    else:
        why = None
    if why:
        return {'id': node['id'], 'hidden': why}
    # ours lets the commentary agent tell its own earlier replies from people's, so it doesn't repeat itself.
    return {'id': node['id'], 'author': author['login'], 'at': node['createdAt'], 'text': clean(node['bodyText']),
            'ours': own(node)}


def threads(number):
    """pack-review's review threads on the PR, open and resolved, each with every comment in it as the agent may
    see it."""
    owner, name = github.repository()
    access = Access(owner, name)
    found = []
    for thread in every('Threads', THREADS, {'owner': owner, 'name': name, 'number': number},
                        lambda data: data['repository']['pullRequest']['reviewThreads']):
        first = thread['comments']
        comments = first['nodes']
        if first['pageInfo']['hasNextPage']:
            comments += every('ThreadComments', THREAD_COMMENTS, {'id': thread['id']},
                              lambda data: data['node']['comments'], first['pageInfo']['endCursor'])
        if not comments or not own(comments[0]):
            continue
        found.append({'id': thread['id'], 'path': clean(thread['path']), 'line': thread['line'],
                      'resolved': thread['isResolved'], 'comments': [shown(node, access) for node in comments]})
    return found
