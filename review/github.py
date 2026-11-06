"""The GitHub GraphQL API, as the review scripts use it. Reads the token, the repo and the API's URL from the
variables GitHub Actions sets."""
import json
import os
import sys
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


def graphql(operation, query, variables):
    """The data GitHub answers the operation with. Stops on any error, naming the operation."""
    request = urllib.request.Request(
        os.environ.get('GITHUB_GRAPHQL_URL', 'https://api.github.com/graphql'),
        data=json.dumps({'operationName': operation, 'query': query, 'variables': variables}).encode(),
        headers={'Authorization': f'bearer {os.environ["GITHUB_TOKEN"]}', 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(request) as response:
            answer = json.load(response)
    except urllib.error.HTTPError as error:
        sys.exit(f'pack-review: GitHub refused {operation} with HTTP {error.code}: {error.read().decode()}')
    if answer.get('errors'):
        sys.exit(f'pack-review: GitHub refused {operation}: '
                 + '; '.join(error['message'] for error in answer['errors']))
    return answer['data']


def nodes(connection, listing):
    """A list's items, stopping if it has another page, since a review that silently missed some would be wrong."""
    if connection['pageInfo']['hasNextPage']:
        sys.exit(f'pack-review: the PR has more than {PAGE} {listing}, and pack-review reads only one page of them.')
    return connection['nodes']


def pull_request(number):
    """The PR's raw data, with every list checked to fit on one page."""
    owner, name = os.environ['GITHUB_REPOSITORY'].split('/')
    found = graphql('PullRequest', PULL_REQUEST, {'owner': owner, 'name': name, 'number': number})
    pr = found['repository']['pullRequest']
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
