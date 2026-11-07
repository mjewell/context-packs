#!/usr/bin/env python3
"""The hooks that keep the review agent from answering before it has read every doc the packs list. `subagent` runs
when a subagent tries to finish, and sends it back to read the docs its prompt names. `answer` runs before the agent
answers, and sends it back to read the docs that neither it nor a finished subagent read. A doc counts as read once
every line of it was returned, by one Read or by several pages. Claude Code passes each hook its input as JSON on
stdin, and reads its decision as JSON on stdout."""
import argparse
import json
from pathlib import Path
import sys

UNREAD = "These docs haven't been read yet:"
# Each gate sends the agent back at most this many times, so an agent that won't read a doc can't loop until the run's
# limit.
SENDS = 3
# How many lines Claude Code's Read returns when it's given no limit.
PAGE = 2000


def entries(transcript):
    return [json.loads(line) for line in Path(transcript).read_text(encoding='utf-8').splitlines() if line]


def lines(transcripts, checkout):
    """The lines of each file in the checkout, by its path from there, that the transcripts' Read calls returned
    without an error."""
    covered = {}
    for transcript in transcripts:
        calls, failed = {}, set()
        for entry in entries(transcript):
            for part in entry['message']['content'] if entry['type'] in ('user', 'assistant') else ():
                if isinstance(part, str) or part['type'] not in ('tool_use', 'tool_result'):
                    continue
                if part['type'] == 'tool_use' and part['name'] == 'Read':
                    calls[part['id']] = part['input']
                elif part['type'] == 'tool_result' and part.get('is_error'):
                    failed.add(part['tool_use_id'])
        for id, input in calls.items():
            path = Path(input['file_path'])
            if id in failed or not path.is_relative_to(checkout):
                continue
            start = max(input.get('offset') or 1, 1)
            covered.setdefault(path.relative_to(checkout).as_posix(), set()).update(
                range(start, start + (input.get('limit') or PAGE)))
    return covered


def read(transcripts, checkout):
    """The paths, from the checkout, of the files whose every line the transcripts' Read calls returned."""
    return {path for path, seen in lines(transcripts, checkout).items()
            if (checkout / path).is_file()
            and set(range(1, len((checkout / path).read_text(encoding='utf-8').splitlines()) + 1)) <= seen}


def prompt(transcript):
    """The text the subagent was started with: its transcript's first message."""
    first = entries(transcript)[0]
    assert first['type'] == 'user' and isinstance(first['message']['content'], str), first
    return first['message']['content']


def sent_back(transcript):
    """How many times the subagent gate has sent the subagent back: Claude Code adds each reason as a message after
    the prompt, which may quote the answer gate's own words."""
    return sum(1 for entry in entries(transcript)[1:] if entry['type'] == 'user'
               and isinstance(entry['message']['content'], str) and UNREAD in entry['message']['content'])


def text(content):
    """A message's or tool result's text: Claude Code writes it as a string, or as a list of parts."""
    return content if isinstance(content, str) else ''.join(part.get('text', '') for part in content)


def denied(transcript):
    """How many times the answer gate has denied the answer: Claude Code returns each reason as the call's error."""
    return sum(1 for entry in entries(transcript) if entry['type'] == 'user' for part in entry['message']['content']
               if not isinstance(part, str) and part['type'] == 'tool_result' and part.get('is_error')
               and UNREAD in text(part['content']))


def unread(docs, then):
    return f'{UNREAD} ' + ', '.join(docs) + f'. Read each one in full and check it against the diff, then {then}.'


def subagent(inputs, docs, hook):
    transcript, checkout = hook['agent_transcript_path'], Path(hook['cwd'])
    # The main transcript leaves out what subagents did, so the answer gate reads their transcripts from this list.
    with (inputs / 'subagents.txt').open('a', encoding='utf-8') as file:
        file.write(f'{transcript}\n')
    given = [doc for doc in docs if doc in prompt(transcript)]
    missing = [doc for doc in given if doc not in read([transcript], checkout)]
    if missing and sent_back(transcript) < SENDS:
        return {'decision': 'block', 'reason': unread(missing, 'finish')}
    return None


def answer(inputs, docs, hook):
    finished = inputs / 'subagents.txt'
    transcripts = {hook['transcript_path'], *(finished.read_text(encoding='utf-8').splitlines()
                                              if finished.exists() else ())}
    done = read(transcripts, Path(hook['cwd']))
    missing = [doc for doc in docs if doc not in done]
    # A step after the agent fails the job while this list exists. It's written at every denial, since an agent sent
    # back can stop without answering again, and it stays when the gate gives up and lets the answer through.
    listed = inputs / 'unread.txt'
    if missing:
        listed.write_text(''.join(f'{doc}\n' for doc in missing), encoding='utf-8')
    elif listed.exists():
        listed.unlink()
    if missing and denied(hook['transcript_path']) < SENDS:
        return {'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'deny',
                                       'permissionDecisionReason': unread(missing, 'answer')}}
    return None


GATES = {'subagent': subagent, 'answer': answer}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('gate', choices=GATES)
    parser.add_argument('--inputs', type=Path, required=True, help='the folder holding docs.txt, the docs to read')
    args = parser.parse_args()
    docs = (args.inputs / 'docs.txt').read_text(encoding='utf-8').splitlines()
    decision = GATES[args.gate](args.inputs, docs, json.load(sys.stdin))
    if decision:
        print(json.dumps(decision))


if __name__ == '__main__':
    main()
