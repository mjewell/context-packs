"""The summary comment pack-review keeps on a PR, from the find job's report: counts for people, and every finding as
JSON for the author's local run. post.py posts it. Only the report's text reaches it, so the only text it holds from
the agent is what the report holds."""
import json
from pathlib import Path

import github

# GitHub's limit on a comment's length.
LIMIT = 65536
# The finding kinds, in the order the summary counts them. Each is a noun that takes an s for more than one.
KINDS = json.loads((Path(__file__).resolve().parent / 'findings.schema.json').read_text(encoding='utf-8'))[
    'properties']['findings']['items']['properties']['kind']['enum']


def counted(findings):
    counts = {kind: sum(f['kind'] == kind for f in findings) for kind in KINDS}
    return ', '.join(f"{n} {kind}{'s' * (n != 1)}" for kind, n in counts.items() if n)


def body(repo, number, report):
    """The summary: the counts for people, and the whole report as JSON. The agent's text appears only in the JSON, where nothing
    renders, so nothing they hold can show people something other than what the author's local
    run reads."""
    findings = report['findings']
    found = counted(findings) or 'nothing'
    text = f"pack-review checked `{report['head'][:7]}` against this repo's context packs and found {found}."
    if findings:
        text += f"\n\nTo go through them, run `/pack-review {repo}#{number}`."
    # Backticks and < only occur inside JSON strings, where \u0060 and \u003c mean the same. So nothing can close the
    # fence, and the block's title, which the local run counts, appears nowhere else.
    data = json.dumps({key: report[key] for key in ('base', 'base_ref', 'head', 'findings')},
                      indent=2, ensure_ascii=False)
    data = data.replace('`', '\\u0060').replace('<', '\\u003c')
    return github.signed(f'{text}\n\n<details><summary>Findings for pack-review</summary>\n\n```json\n{data}\n'
                         '```\n\n</details>')
