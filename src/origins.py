"""Fetch context packs from their git origins, through a cache of bare clones that every sync shares."""
import io
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile

COMMIT = re.compile(r'[0-9a-f]{40}')


def git(*args):
    result = subprocess.run(['git', *args], capture_output=True)
    if result.returncode != 0:
        sys.exit(f'context-packs: git {" ".join(args)} failed:\n{result.stderr.decode().strip()}')
    return result.stdout.decode().strip()


def clone(url):
    """The cached bare clone of url, cloning it the first time."""
    cache = Path(os.environ.get('XDG_CACHE_HOME') or Path.home() / '.cache') / 'context-packs'
    folder = cache / re.sub(r'[^A-Za-z0-9._-]+', '_', url)
    if not folder.exists():
        cache.mkdir(parents=True, exist_ok=True)
        git('clone', '--quiet', '--bare', url, str(folder))
    return folder


def commit(folder, ref):
    """The full commit ref names in the clone at folder, or None if it names none."""
    result = subprocess.run(['git', '--git-dir', str(folder), 'rev-parse', '--verify', '--quiet', f'{ref}^{{commit}}'],
                            capture_output=True)
    return result.stdout.decode().strip() if result.returncode == 0 else None


def fetched(url, ref):
    """The cached clone of url, fetched until it has ref, or None if the origin has no such commit or tag."""
    folder = clone(url)
    if not commit(folder, ref):
        git('--git-dir', str(folder), 'fetch', '--quiet', 'origin', '+refs/heads/*:refs/heads/*',
            '+refs/tags/*:refs/tags/*')
    return folder if commit(folder, ref) else None


def remote(url, kind):
    """url's tags or branches, by name."""
    lines = git('ls-remote', f'--{kind}', '--refs', url).splitlines()
    return {ref.split('/', 2)[2]: sha for sha, ref in (line.split('\t') for line in lines)}


def tip(url):
    """The commit at the tip of url's default branch."""
    head = git('ls-remote', url, 'HEAD').split()
    if not head:
        sys.exit(f'context-packs: {url} has no default branch to pin to.')
    return head[0]


def pin(url, ref):
    """ref as a pack's marker holds it: a tag stays a tag, and a commit becomes its full hash."""
    if ref in remote(url, 'tags'):
        return ref
    if ref in remote(url, 'heads'):
        sys.exit(f'context-packs: {ref} is a branch in {url}, and a branch moves. Pin to a tag or a commit, '
                 'or leave out --ref to follow the default branch on update.')
    folder = fetched(url, ref)
    if not folder:
        sys.exit(f'context-packs: {url} has no tag or commit {ref}.')
    return commit(folder, ref)


def latest(url, ref):
    """Where an update moves a pack pinned to ref: a commit to the tip of the default branch, and a tag nowhere."""
    return tip(url) if COMMIT.fullmatch(ref) else ref


def extract(url, ref, path, into):
    """Write the folder at path in url, as of ref, into the folder into, and return where it landed."""
    folder = fetched(url, ref)
    if not folder:
        sys.exit(f'context-packs: {url} has no tag or commit {ref}. Pin the pack to one that exists, then sync again.')
    archive = subprocess.run(['git', '--git-dir', str(folder), 'archive', '--format=tar', ref, '--', path or '.'],
                             capture_output=True)
    if archive.returncode != 0:
        sys.exit(f'context-packs: {url} has no folder {path} at {ref}:\n{archive.stderr.decode().strip()}')
    with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
        tar.extractall(into)
    return into / path
