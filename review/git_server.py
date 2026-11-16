#!/usr/bin/env python3
"""An MCP server over stdio that lets the review agent read the change it reviews, from the merge base to the head,
without a shell. Each tool runs one fixed git command, and nothing the agent sends reaches git as an option."""
import argparse
import json
import re
import subprocess
import sys

PATH = {'type': 'string', 'description': 'A path from the repo root.'}
PAGE = {'type': 'integer', 'minimum': 1, 'description': 'Which page to return, from 1.'}
# How many lines a tool returns at most, so one call can't fill the agent's context.
LINES = 1000
HUNK = re.compile(r'@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@')
TOOLS = {
    'changed': ('Every path the change touches, with how many lines its diff has.', {}, []),
    'diff': ("One path's diff from the merge base to the head. Each line the head has starts with its line number "
             'there.', {'path': PATH, 'page': PAGE}, ['path']),
    'log': ("The change's commits, newest first, with their messages: every one, or the ones that touched a path.",
            {'path': PATH, 'page': PAGE}, []),
}


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

    def log(self, path=None, page=1):
        paths = ['--', checked(path)] if path is not None else []
        return paged('the log', git('log', '--no-decorate', '--format=medium', f'{self.start}..{self.head}',
                                    *paths).splitlines(), page)

    def diff(self, path, page=1):
        if checked(path) not in self.paths():
            raise Refused(f"{path} isn't one of the paths changed() lists.")
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
    more = f': call again with page {page + 1} for more' if page < count else ''
    return f'{text}(page {page} of {count}{more})\n'


class Refused(Exception):
    """A call the server won't run, with the reason for the agent."""


def checked(path):
    """The path, once it's a path from the repo root that doesn't climb out of it."""
    if not path or path.startswith('/') or '..' in path.split('/'):
        raise Refused(f'{path!r} must be a path from the repo root, without "..".')
    return path


def allowed(name, arguments):
    """The arguments, once the tool's schema allows them."""
    if name not in TOOLS:
        raise Refused(f'There is no tool named {name}.')
    _, properties, required = TOOLS[name]
    for key in required:
        if key not in arguments:
            raise Refused(f'{name} needs {key}.')
    for key, value in arguments.items():
        if key not in properties:
            raise Refused(f'{name} takes no {key}.')
        kind = properties[key]['type']
        # A bool is an int in Python, but not an integer in JSON.
        if not isinstance(value, {'string': str, 'integer': int}[kind]) or isinstance(value, bool):
            raise Refused(f'{name} needs {key} as {"a string" if kind == "string" else "an integer"}.')
        if value < properties[key].get('minimum', value):
            raise Refused(f'{name} needs {key} to be at least {properties[key]["minimum"]}.')
    return arguments


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


def listed():
    return [{'name': name, 'description': description,
             'inputSchema': {'type': 'object', 'properties': properties, 'required': required,
                             'additionalProperties': False}}
            for name, (description, properties, required) in TOOLS.items()]


def answer(change, message):
    """The response to one request."""
    method = message['method']
    if method == 'tools/call':
        params = message['params']
        name, arguments = params['name'], params.get('arguments', {})
        try:
            # allowed() runs first, so only a name in TOOLS reaches getattr, and no other method of Change runs.
            arguments = allowed(name, arguments)
            text, error = getattr(change, name)(**arguments), False
        except Refused as refused:
            text, error = str(refused), True
        result = {'content': [{'type': 'text', 'text': text}], 'isError': error}
    elif method == 'initialize':
        result = {'protocolVersion': message['params']['protocolVersion'], 'capabilities': {'tools': {}},
                  'serverInfo': {'name': 'pack-review-git', 'version': '1'}}
    elif method == 'tools/list':
        result = {'tools': listed()}
    elif method == 'ping':
        result = {}
    else:
        return {'jsonrpc': '2.0', 'id': message['id'],
                'error': {'code': -32601, 'message': f'no such method: {method}'}}
    return {'jsonrpc': '2.0', 'id': message['id'], 'result': result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', required=True, help='the commit the reviewed change starts from')
    parser.add_argument('--head', required=True, help='the commit that is reviewed')
    parser.add_argument('command', nargs='?', choices=['shown'],
                        help='print as JSON the head lines each diff shows, for new threads to be left on, and stop')
    args = parser.parse_args()
    change = Change(args.base, args.head)
    if args.command == 'shown':
        print(json.dumps(change.shown()))
        return
    for line in sys.stdin:
        message = json.loads(line)
        # A notification has no id and gets no response.
        if 'id' in message:
            print(json.dumps(answer(change, message)), flush=True)


if __name__ == '__main__':
    main()
