"""The text pack-review posts in review threads, written for people. The comment a thread opens with says what was
found, and a later run's pairing agent reads that same text to tell whether a new finding is about the same issue.
The agent's text renders as Markdown, defused so it can't notify anyone or hide text."""
import re

import github

# Each kind's label, set in code like the commit's, so both read as tags at the start of the comment.
LABELS = {'deviates': 'deviation', 'conflicting': 'conflict', 'uncovered': 'uncovered choice'}
# A GitHub mention: a login, or an org's team, after an @ that doesn't end a word, as in an email address.
MENTION = re.compile(r'(?<![\w`])@[A-Za-z0-9][A-Za-z0-9-]*(?:/[A-Za-z0-9_.-]+)?')


def defused(text):
    """The agent's text as Markdown that can't notify anyone or hide text: each mention is wrapped in backticks, and
    each < is escaped, so no HTML comment or tag can form."""
    return MENTION.sub(lambda found: f'`{found.group(0)}`', text).replace('<', '&lt;')


def quoted(text):
    """The agent's text, defused, as a quote block."""
    return '\n'.join(f'> {line}' if line else '>' for line in defused(text).split('\n'))


def body(finding, head):
    """The comment that opens a thread for the finding: what it is, the rules it quotes, and the take."""
    parts = [f"`{LABELS[finding['kind']]}` `{head[:7]}` **{defused(finding['headline'])}**"]
    parts += [f"From `{defused(rule['file'])}`:\n\n{quoted(rule['quote'])}" for rule in finding['rules']]
    parts.append(defused(finding['take']))
    return github.signed('\n\n'.join(parts))
