"""Remove from a GitHub comment what a reader of the rendered comment wouldn't see, and redact secrets. It runs on what
the review agent reads, since hidden text in a comment can carry instructions to it, and on what it writes, since a
later run reads that. Each rule removes a whole class of hidden content rather than known tricks, so it needs no
list kept up to date: raw HTML, which these comments don't need, Markdown image alt text and link titles, and every
Unicode format character. Code is left as written, since markup inside it shows as text."""
import re
import unicodedata

FENCE = re.compile(r'^(`{3,}|~{3,})[^\n]*\n.*?(?:^\1[ \t]*$|\Z)', re.M | re.S)
INLINE = re.compile(r'(?<!`)(`+)(?!`).*?(?<!`)\1(?!`)', re.S)
HIDDEN = [
    (re.compile(r'<!--.*?(?:-->|\Z)', re.S), ''),
    (re.compile(r'</?[A-Za-z][A-Za-z0-9-]*(?:\s[^<>]*)?/?>'), ''),
    (re.compile(r'!\[[^\]]*\](?=[(\[])'), '![]'),
    (re.compile(r'(\]\([^)\s]+)\s+(?:"[^"]*"|\'[^\']*\'|\([^)]*\))\)'), r'\1)'),
]
SECRETS = re.compile(r'sk-ant-[A-Za-z0-9_-]+|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}')


def prose(text):
    for pattern, replacement in HIDDEN:
        text = pattern.sub(replacement, text)
    return text


def outside(pattern, text, apply):
    """The text with apply run on the parts the pattern doesn't match."""
    parts, end = [], 0
    for match in pattern.finditer(text):
        parts += [apply(text[end:match.start()]), match.group(0)]
        end = match.end()
    return ''.join(parts + [apply(text[end:])])


def clean(text):
    text = outside(FENCE, text, lambda part: outside(INLINE, part, prose))
    text = ''.join(c for c in text if unicodedata.category(c) != 'Cf')
    return SECRETS.sub('[redacted]', text).strip()
