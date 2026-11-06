"""GitHub's API, as the review scripts use it. Reads the token, the repo and the API's URLs from the variables GitHub
Actions sets."""
import json
import os
import urllib.error
import urllib.request

# Ends every comment pack-review writes, so its own comments can be told from others the same token wrote.
MARKER = '<!-- pack-review -->'
# Roles on the repo whose comments the review agent reads. Anyone can comment on a public repo.
TRUSTED = {'OWNER', 'MEMBER', 'COLLABORATOR'}
PAGE = 100

COMMENT = 'author { login } authorAssociation viewerDidAuthor body'
PULL_REQUEST = f'''
query PullRequest($owner: String!, $name: String!, $number: Int!) {{
  repository(owner: $owner, name: $name) {{
    pullRequest(number: $number) {{
      id title body authorAssociation author {{ login }} baseRefOid headRefOid
      comments(first: {PAGE}) {{ pageInfo {{ hasNextPage }} nodes {{ id {COMMENT} }} }}
      reviews(first: {PAGE}) {{ pageInfo {{ hasNextPage }} nodes {{ state {COMMENT} }} }}
      reviewThreads(first: {PAGE}) {{
        pageInfo {{ hasNextPage }}
        nodes {{
          id isResolved isOutdated path line
          comments(first: {PAGE}) {{ pageInfo {{ hasNextPage }} nodes {{ {COMMENT} }} }}
        }}
      }}
    }}
  }}
}}'''


class GitHubError(Exception):
    """GitHub refused a request, or answered with more than pack-review reads."""


def repository():
    return os.environ['GITHUB_REPOSITORY'].split('/')


def send(url, body, what):
    request = urllib.request.Request(url, data=json.dumps(body).encode(), headers={
        'Authorization': f'bearer {os.environ["GITHUB_TOKEN"]}', 'Content-Type': 'application/json',
        'Accept': 'application/vnd.github+json'})
    try:
        with urllib.request.urlopen(request) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        answer = error.read().decode()
        try:
            found = json.loads(answer)
            answer = '; '.join([found.get('message', '')] + [e.get('message', str(e))
                                                            for e in found.get('errors', [])])
        except ValueError:
            pass
        raise GitHubError(f'GitHub refused {what} with HTTP {error.code}: {answer}') from None


def graphql(operation, query, variables):
    """The data GitHub answers the operation with."""
    url = os.environ.get('GITHUB_GRAPHQL_URL', 'https://api.github.com/graphql')
    answer = send(url, {'operationName': operation, 'query': query, 'variables': variables}, operation)
    if answer.get('errors'):
        raise GitHubError(f'GitHub refused {operation}: ' + '; '.join(e['message'] for e in answer['errors']))
    return answer['data']


def post(path, body):
    """POST to a REST path under the repo, such as pulls/7/comments."""
    owner, name = repository()
    url = f'{os.environ.get("GITHUB_API_URL", "https://api.github.com")}/repos/{owner}/{name}/{path}'
    return send(url, body, f'POST {path}')


def nodes(connection, listing):
    """A list's items, refusing one with another page, since a review that silently missed some would be wrong."""
    if connection['pageInfo']['hasNextPage']:
        raise GitHubError(f'The PR has more than {PAGE} {listing}, and pack-review reads only one page of them.')
    return connection['nodes']


def pull_request(number):
    """The PR's raw data, with every list checked to fit on one page."""
    owner, name = repository()
    pr = graphql('PullRequest', PULL_REQUEST, {'owner': owner, 'name': name, 'number': number})
    pr = pr['repository']['pullRequest']
    pr['comments'] = nodes(pr['comments'], 'comments')
    pr['reviews'] = nodes(pr['reviews'], 'reviews')
    pr['reviewThreads'] = nodes(pr['reviewThreads'], 'review threads')
    for thread in pr['reviewThreads']:
        thread['comments'] = nodes(thread['comments'], f'comments of review thread {thread["id"]}')
    return pr


def own(comment):
    """Whether pack-review wrote the comment: the token's identity wrote it, and it ends with the marker."""
    return comment['viewerDidAuthor'] and comment['body'].rstrip().endswith(MARKER)


def trusted(comment):
    return comment['authorAssociation'] in TRUSTED


def started(pr):
    """The ids of the threads pack-review started."""
    return {thread['id'] for thread in pr['reviewThreads'] if own(thread['comments'][0])}


def signed(body):
    """A comment as pack-review posts it: marked as Claude's for people, and as pack-review's for the next run."""
    return f'🤖 {body}\n\n{MARKER}'
