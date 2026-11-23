#!/usr/bin/env python3
"""The change a review reads, from the merge base of a base commit to a head commit, as fixed git commands. Nothing
a caller passes reaches git as an option, so the wizard can hand it a path or a page as an agent typed them. Run as a
script, `shown` prints the head lines each diff shows, for the report to pick where each new thread opens."""
import argparse
import json
import re
import subprocess

# How many lines a tool returns at most, so one call can't fill the agent's context.
LINES = 1000
HUNK = re.compile(r'@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@')


class Change:
    """The change from the merge base of a base commit to a head commit, which every tool reads from."""

    def __init__(self, base, head):
        self.base, self.head = commit(base), commit(head)
        self.range = f'{self.base}...{self.head}'
        self.start = git('merge-base', self.base, self.head).strip()

    def paths(self):
        out = git('diff', '--name-only', '-z', '--no-renames', self.range)
        return [path for path in out.split('\0') if path]

    def raw(self, path):
        return git('diff', '--no-ext-diff', '--no-textconv', '--no-renames', self.range, '--', path).splitlines()

    def shown(self):
        """The head lines each path's diff shows, which a review comment can be left on."""
        return {path: [n for n, _ in marked(self.raw(path)) if n] for path in self.paths()}

    def lines(self, path):
        """The path's diff, each line numbered as numbered() says."""
        return numbered(self.raw(path))

    def changed(self):
        return ''.join(f'{len(self.lines(path))}\t{path}\n' for path in self.paths())

    def log(self, page=1):
        return paged('the log', git('log', '--no-decorate', '--format=medium', f'{self.start}..{self.head}')
                     .splitlines(), page)

    def diff(self, path, page=1):
        if checked(path) not in self.paths():
            raise Refused(f"{path} isn't one of the paths the change touches.")
        return paged(path, self.lines(path), page)


def pages(count):
    """How many pages a tool's output of count lines takes."""
    return max(-(-count // LINES), 1)


def paged(name, lines, page):
    """One page of the lines, with a line after it that says where it is when there's more than one."""
    count = pages(len(lines))
    if page > count:
        raise Refused(f'{name} has {count} pages.')
    text = ''.join(f'{line}\n' for line in lines[(page - 1) * LINES:page * LINES])
    if count == 1:
        return text
    more = f': run it again with page {page + 1} for more' if page < count else ''
    return f'{text}(page {page} of {count}{more})\n'


class Refused(Exception):
    """A call the server won't run, with the reason for the agent."""


def checked(path):
    """The path, once it's a path from the repo root that doesn't climb out of it."""
    if not path or path.startswith('/') or '..' in path.split('/'):
        raise Refused(f'{path!r} must be a path from the repo root, without "..".')
    return path


def marked(diff):
    """Each line of a diff with the head's line number for it: a number for a line in a hunk that the head has, '' for
    another line in a hunk, and None for a header or hunk line."""
    marks, number = [], None
    for line in diff:
        found = HUNK.match(line)
        if found:
            number = int(found.group(1))
            marks.append((None, line))
        elif line[:1] not in (' ', '+', '-', '\\'):
            # Every line in a hunk starts with one of those, so this one starts the next file's header.
            number = None
            marks.append((None, line))
        elif number is None:
            marks.append((None, line))
        elif line[:1] in (' ', '+'):
            marks.append((number, line))
            number += 1
        else:
            marks.append(('', line))
    return marks


def numbered(diff):
    """A diff's lines, with each line in a hunk that the head has led by its line number there, and every other line
    in a hunk led by blanks, so the agent copies a line number instead of counting. The header and hunk lines stay
    as git wrote them."""
    marks = marked(diff)
    width = max((len(str(n)) for n, _ in marks if n), default=0)
    return [line if n is None else f'{n:>{width}} {line}' for n, line in marks]


def git(*args):
    """What git printed. Every argument is fixed here or already checked, so none is the agent's text as an
    option."""
    run = subprocess.run(['git', '--literal-pathspecs', *args], capture_output=True, text=True, errors='replace')
    if run.returncode:
        raise Refused(f'git said: {run.stderr.strip()}')
    return run.stdout


def commit(rev):
    """The hash of the commit rev names. --end-of-options, and the ^{commit} after rev, keep rev from being read as
    an option."""
    return git('rev-parse', '--verify', '--end-of-options', f'{rev}^{{commit}}').strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--base', required=True, help='the commit the reviewed change starts from')
    parser.add_argument('--head', required=True, help='the commit that is reviewed')
    parser.add_argument('command', choices=['shown'], help='print as JSON the head lines each diff shows')
    args = parser.parse_args()
    print(json.dumps(Change(args.base, args.head).shown()))


if __name__ == '__main__':
    main()
