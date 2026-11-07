"""Remove invisible characters from the review agent's findings, and redact secrets, before they're posted. The
findings appear only in the summary's JSON code block, where every other character shows as written, so people and
the author's local run see the same text."""
import re
import unicodedata

SECRETS = re.compile(r'sk-ant-[A-Za-z0-9_-]+|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}')


def clean(text):
    text = ''.join(c for c in text if unicodedata.category(c) != 'Cf')
    return SECRETS.sub('[redacted]', text).strip()
