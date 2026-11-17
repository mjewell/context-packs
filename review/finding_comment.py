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

# Said after a rule's file only when its doc wasn't routed, since routed is the usual case.
UNROUTED = ", whose `when` didn't match this change"


def defused(text):
    """The agent's text as Markdown that can't notify anyone or hide text: each @ that could start a mention has a word
    joiner after it, and each < is escaped, so no HTML comment or tag can form."""
    return MENTION.sub('@' + JOINER, text).replace('<', '&lt;')


def quoted(text):
    """The agent's text, defused, as a quote block."""
    return '\n'.join(f'> {line}' if line else '>' for line in defused(text).split('\n'))


def listed(title, items):
    """The agent's items, defused, as a list under a title."""
    return f'{title}:\n\n' + '\n'.join(f'- {defused(item)}' for item in items)


def body(finding, head, anchor):
    """The comment that opens a thread for the finding on its anchor's line: what it is, the rules it quotes, where
    else it was found, the signs it's deliberate, how the code makes an uncovered choice now, and the take."""
    # The kind is set in code like the commit, so both read as tags at the start of the comment.
    parts = [f"`{finding['kind']}` `{head[:7]}` **{defused(finding['headline'])}**"]
    parts += [f"From `{defused(rule['file'])}`{'' if rule['routed'] else UNROUTED}:\n\n{quoted(rule['quote'])}"
              for rule in finding['rules']]
    # The thread's own line shows one spot. The anchor can be a spot that follows the rule, when the diff shows no
    # deviating one, so every deviating spot but the anchor is named.
    others = [spot for spot in finding['spots']
              if not spot['follows'] and (spot['path'], spot['line']) != (anchor['path'], anchor['line'])]
    if others:
        parts.append('Also found at ' + ', '.join(f"`{defused(spot['path'])}:{spot['line']}`" for spot in others) + '.')
    if finding['deliberate']:
        parts.append(listed('Signs it may be deliberate', finding['deliberate']))
    if finding['exemplars']:
        parts.append(listed('How the code does it now', [
            f"{exemplar['way']}: " + ', '.join(f'`{example}`' for example in exemplar['examples'])
            for exemplar in finding['exemplars']]))
    parts.append(defused(finding['take']))
    return github.signed('\n\n'.join(parts))
