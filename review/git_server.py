#!/usr/bin/env python3
"""An MCP server over stdio that lets the review agent read the change it reviews, from the merge base to the head,
without a shell. Each tool runs one fixed git command, and nothing the agent sends reaches git as an option."""
import argparse
import json
import sys

from change import Change, Refused

PATH = {'type': 'string', 'description': 'A path from the repo root.'}
PAGE = {'type': 'integer', 'minimum': 1, 'description': 'Which page to return, from 1.'}
TOOLS = {
    'changed': ('Every path the change touches, with how many lines its diff has.', {}, []),
    'diff': ("One path's diff from the merge base to the head. Each line the head has starts with its line number "
             'there.', {'path': PATH, 'page': PAGE}, ['path']),
    'log': ("The change's commits, newest first, with their messages: every one, or the ones that touched a path.",
            {'path': PATH, 'page': PAGE}, []),
}


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
