/**
 * The summary comment pack-review keeps on a PR, from the find job's report: counts for people, and every finding as
 * JSON for the author's local run. post.ts posts it. Only the report's text reaches it, so the only text it holds from
 * the agent is what the report holds.
 */
import { type Anchor, type Finding, KINDS, type Report } from './finding.ts';
import * as findingComment from './finding_comment.ts';
import * as github from './github.ts';

// GitHub's limit on a comment's length.
export const LIMIT = 65536;
// The findings block's title, which a local run finds the summary by and reads the JSON after.
export const TITLE = 'Findings for pack-review';

function counted(findings: readonly Finding[]): string {
  return KINDS.map((kind): [string, number] => [kind, findings.filter((f) => f.kind === kind).length])
    .filter(([, n]) => n)
    .map(([kind, n]) => `${n} ${kind}${n !== 1 ? 's' : ''}`)
    .join(', ');
}

/**
 * The finding's line in the list for people: its kind, its headline escaped as thread text is, and where its thread
 * is. The headline is kept on one line and always followed by more text, since the local run takes the JSON from after
 * the first "Findings for pack-review" and a line break.
 */
function listed(finding: Finding, anchor: Anchor): string {
  const where = anchor ? `at \`${findingComment.escaped(anchor.path)}:${anchor.line}\`` : 'on no line the diff shows';
  return `- \`${finding.kind}\` ${findingComment.escaped(finding.headline.split(/\s+/).filter(Boolean).join(' '))}, ${where}`;
}

/**
 * The summary: the counts and a line for each finding for people, and the whole report as JSON for the local run. The
 * listed headlines are escaped as thread text is, so they can't notify anyone or hide text.
 */
export function body(repo: string, number: number, report: Report): string {
  const findings = report.findings;
  let text =
    `pack-review checked \`${report.head.slice(0, 7)}\` against this repo's context packs and found ` +
    `${counted(findings) || 'nothing'}.`;
  if (findings.length) {
    text += `\n\n${findings.map((finding, n) => listed(finding, report.anchors[n] ?? null)).join('\n')}`;
    text += `\n\nTo go through them, run \`/pack-review ${repo}#${number}\`.`;
  }
  // Backticks and < only occur inside JSON strings, where ` and < mean the same. So nothing can close the
  // fence, and the block's title, which the local run counts, appears nowhere else.
  const data = JSON.stringify({ base: report.base, base_ref: report.base_ref, head: report.head, findings }, null, 2)
    .replaceAll('`', '\\u0060')
    .replaceAll('<', '\\u003c');
  return github.signed(`${text}\n\n<details><summary>${TITLE}</summary>\n\n\`\`\`json\n${data}\n\`\`\`\n\n</details>`);
}
