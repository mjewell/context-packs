/**
 * The text pack-review posts in review threads, written for people. The comment a thread opens with says what was
 * found, and a later run's pairing agent reads that same text to tell whether a new finding is about the same issue.
 * The agent's text renders as Markdown, escaped so it can't notify anyone or hide text.
 */
import * as github from './github.ts';
import type { Finding } from './report.ts';

// GitHub links a mention only when a login's first character follows the @. A word joiner between them doesn't show,
// and it breaks the mention whatever Markdown is around it. Backticks around the mention wouldn't hold, since the
// agent's own backticks can pair with them.
const MENTION = /@(?=[A-Za-z0-9])/g;
const JOINER = '⁠';

// Said after a rule's file only when its doc wasn't routed, since routed is the usual case.
const UNROUTED = ", whose `when` didn't match this change";

export interface Rule {
  readonly file: string;
  readonly quote: string;
  readonly routed: boolean;
}

export interface Exemplar {
  readonly way: string;
  readonly examples: string[];
}

/**
 * The agent's text as Markdown that can't notify anyone or hide text: each @ that could start a mention has a word
 * joiner after it, and each < is escaped, so no HTML comment or tag can form.
 */
export function escaped(text: string): string {
  return text.replace(MENTION, `@${JOINER}`).replaceAll('<', '&lt;');
}

/** The agent's text, escaped, as a quote block. */
export function quoted(text: string): string {
  return escaped(text)
    .split('\n')
    .map((line) => (line ? `> ${line}` : '>'))
    .join('\n');
}

/** The agent's items, escaped, as a list under a title. */
function listed(title: string, items: readonly string[]): string {
  return `${title}:\n\n` + items.map((item) => `- ${escaped(item)}`).join('\n');
}

/**
 * The comment that opens a thread for the finding on its anchor's line: what it is, the rules it quotes, where else it
 * was found, the signs it's deliberate, how the code makes an uncovered choice now, and the take.
 */
export function body(finding: Finding, head: string, anchor: { readonly path: string; readonly line: number }): string {
  // The kind is set in code like the commit, so both read as tags at the start of the comment.
  const parts = [`\`${finding.kind}\` \`${head.slice(0, 7)}\` **${escaped(finding.headline)}**`];
  parts.push(
    ...(finding.rules as Rule[]).map(
      (rule) => `From \`${escaped(rule.file)}\`${rule.routed ? '' : UNROUTED}:\n\n${quoted(rule.quote)}`,
    ),
  );
  // The thread's own line shows one spot. The anchor can be a spot that follows the rule, when the diff shows no
  // deviating one, so every deviating spot but the anchor is named.
  const others = finding.spots.filter(
    (spot) => !spot.follows && !(spot.path === anchor.path && spot.line === anchor.line),
  );
  if (others.length)
    parts.push('Also found at ' + others.map((spot) => `\`${escaped(spot.path)}:${spot.line}\``).join(', ') + '.');
  if (finding.deliberate.length) parts.push(listed('Signs it may be deliberate', finding.deliberate as string[]));
  if (finding.exemplars.length) {
    parts.push(
      listed(
        'How the code does it now',
        (finding.exemplars as Exemplar[]).map(
          (exemplar) => `${exemplar.way}: ` + exemplar.examples.map((example) => `\`${example}\``).join(', '),
        ),
      ),
    );
  }
  parts.push(escaped(finding.take));
  return github.signed(parts.join('\n\n'));
}
