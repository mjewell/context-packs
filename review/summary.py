"""The summary comment pack-review keeps on a PR, from the find job's report: counts for people, and every finding as
JSON for the author's local run. post.py posts it. Only the report's text reaches it, so the only text it holds from
the agent is what the report holds."""
import json
from pathlib import Path

import finding_comment
import github

# GitHub's limit on a comment's length.
LIMIT = 65536
# The finding kinds, in the order the summary counts them. Each is a noun that takes an s for more than one.
KINDS = json.loads((Path(__file__).resolve().parent / 'findings.schema.json').read_text(encoding='utf-8'))[
    'properties']['findings']['items']['properties']['kind']['enum']


def counted(findings):
    counts = {kind: sum(f['kind'] == kind for f in findings) for kind in KINDS}
    return ', '.join(f"{n} {kind}{'s' * (n != 1)}" for kind, n in counts.items() if n)


def listed(finding, anchor):
    """The finding's line in the list for people: its kind, its headline escaped as thread text is, and where its
    thread is. The headline is kept on one line and always followed by more text, since the local run takes the JSON
    from after the first "Findings for pack-review" and a line break."""
    where = f"at `{finding_comment.escaped(anchor['path'])}:{anchor['line']}`" if anchor else 'on no line the diff shows'
    return f"- `{finding['kind']}` {finding_comment.escaped(' '.join(finding['headline'].split()))}, {where}"


def body(repo, number, report):
    """The summary: the counts and a line for each finding for people, and the whole report as JSON for the local run.
    The listed headlines are escaped as thread text is, so they can't notify anyone or hide text."""
    findings = report['findings']
    found = counted(findings) or 'nothing'
    text = f"pack-review checked `{report['head'][:7]}` against this repo's context packs and found {found}."
    if findings:
        text += '\n\n' + '\n'.join(listed(finding, anchor) for finding, anchor in zip(findings, report['anchors']))
    if findings:
        text += f"\n\nTo go through them, run `/pack-review {repo}#{number}`."
    # Backticks and < only occur inside JSON strings, where \u0060 and \u003c mean the same. So nothing can close the
    # fence, and the block's title, which the local run counts, appears nowhere else.
    data = json.dumps({key: report[key] for key in ('base', 'base_ref', 'head', 'findings')},
                      indent=2, ensure_ascii=False)
    data = data.replace('`', '\\u0060').replace('<', '\\u003c')
    return github.signed(f'{text}\n\n<details><summary>Findings for pack-review</summary>\n\n```json\n{data}\n'
                         '```\n\n</details>')
