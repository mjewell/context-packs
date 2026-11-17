"""The text pack-review posts in review threads, written for people. The comment a thread opens with says what was
found, and a later run's pairing agent reads that same text to tell whether a new finding is about the same issue.
The agent's text renders as Markdown, defused so it can't notify anyone or hide text."""
import re

import github

# GitHub links a mention only when a login's first character follows the @. A word joiner between them doesn't show,
# and it breaks the mention whatever Markdown is around it. Backticks around the mention wouldn't hold, since the
# agent's own backticks can pair with them.
MENTION = re.compile(r'@(?=[A-Za-z0-9])')
JOINER = '\u2060'


def defused(text):
    """The agent's text as Markdown that can't notify anyone or hide text: each @ that could start a mention has a word
    joiner after it, and each < is escaped, so no HTML comment or tag can form."""
    return MENTION.sub('@' + JOINER, text).replace('<', '&lt;')


def quoted(text):
    """The agent's text, defused, as a quote block."""
    return '\n'.join(f'> {line}' if line else '>' for line in defused(text).split('\n'))


def body(finding, head):
    """The comment that opens a thread for the finding: what it is, the rules it quotes, and the take."""
    # The kind is set in code like the commit, so both read as tags at the start of the comment.
    parts = [f"`{finding['kind']}` `{head[:7]}` **{defused(finding['headline'])}**"]
    parts += [f"From `{defused(rule['file'])}`:\n\n{quoted(rule['quote'])}" for rule in finding['rules']]
    parts.append(defused(finding['take']))
    return github.signed('\n\n'.join(parts))
