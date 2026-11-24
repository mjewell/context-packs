/**
 * A parsed spec tree as one HTML page, with every level below the top collapsed. `[[slug]]` links jump to the node
 * with that ID and open its ancestors. Mermaid blocks render in the browser when their node is opened. D2 blocks render
 * to SVG here, through the `d2` CLI, which must be installed when a tree has one. Node's standard library only.
 */
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

import { collectIds, LINK_SOURCE, labelOf, type Node, nodes, type Root, strip } from './tree_model.ts';

const MERMAID = 'https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.esm.min.mjs';
// ELK lays out nested containers more tidily than D2's default, and its spacing is tightened so a diagram stays small.
// Theme 200 is D2's dark theme, which the SVG switches to through prefers-color-scheme.
const D2_ARGS = [
  '--layout',
  'elk',
  '--elk-nodeNodeBetweenLayers',
  '30',
  '--elk-edgeNodeBetweenLayers',
  '15',
  '--elk-padding',
  '[top=20,left=12,bottom=12,right=12]',
  '--theme',
  '0',
  '--dark-theme',
  '200',
  '--pad',
  '4',
  '-',
  '-',
];
// Smaller text than D2's 16px default, set here so a tree's diagrams don't each repeat it.
const D2_STYLE = '**.style.font-size: 13\n(** -> **)[*].style.font-size: 12\n';
const SCHEME = /^[a-z][a-z0-9+.-]*:/i;
const SAFE_SCHEMES = new Set(['http:', 'https:', 'mailto:']);
// The page, its script, and its comments, which a person leaves on nodes and copies to an agent. The comments' pure
// logic is a module node can test, and the page inlines it ahead of the code that wires it to the page.
const read = (name: string) => fs.readFileSync(path.join(import.meta.dirname, name), 'utf8');
const TEMPLATE = read('tree_page.html');
const SCRIPT = `\n${read('tree_page.js')}`;
const COMMENTS_SCRIPT = read('tree_comments.mjs') + read('tree_comments_ui.js');
const COMMENTS_CSS = read('tree_comments.css');

const LINK_WHOLE = new RegExp(`^${LINK_SOURCE}$`, 'u');
// The link's groups made non-capturing, so splitting on it keeps each part whole, as re.split does with one group.
const PARTS = new RegExp(`(${LINK_SOURCE.replace(/\((?!\?)/g, '(?:')}|\`[^\`]*\`)`, 'u');

/** Stops the render with a message for the person who ran it. */
export class Stop extends Error {}

/** text with &, <, >, " and ' escaped, as Python's html.escape escapes them. */
function escapeHtml(text: string): string {
  return text
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#x27;');
}

const NAMED: Readonly<Record<string, string>> = { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'" };

/**
 * text with its character references decoded, as a browser decodes an attribute: numeric ones, and the five names
 * escapeHtml() writes. Any other named reference stops the render, since it could spell out a scheme, such as
 * javascript&colon;, that the link check has to see.
 */
function unescapeHtml(text: string, what: string): string {
  return text.replace(/&(#[0-9]+|#[xX][0-9a-fA-F]+|[A-Za-z][A-Za-z0-9]*);?/g, (match, ref: string) => {
    if (ref.startsWith('#')) {
      const code = ref[1] === 'x' || ref[1] === 'X' ? parseInt(ref.slice(2), 16) : parseInt(ref.slice(1), 10);
      return code > 0 && code <= 0x10ffff ? String.fromCodePoint(code) : '�';
    }
    const named = NAMED[ref];
    if (named === undefined) throw new Stop(`trees.ts: ${what} holds ${match}, which the page can't check.`);
    return named;
  });
}

/** Python's repr of a string, for an error that shows a URL as it is. */
function repr(text: string): string {
  // biome-ignore lint/suspicious/noControlCharactersInRegex: repr writes each control character as an escape.
  const escaped = text.replace(/\\/g, '\\\\').replace(/[\x00-\x1f\x7f]/g, (c) => {
    const special: Record<string, string> = { '\n': '\\n', '\r': '\\r', '\t': '\\t' };
    return special[c] ?? `\\x${c.charCodeAt(0).toString(16).padStart(2, '0')}`;
  });
  return text.includes("'") && !text.includes('"') ? `"${escaped}"` : `'${escaped.replaceAll("'", "\\'")}'`;
}

/** Escape, then render code spans, bold, Markdown links, and [[slug]] and [[slug|text]] links. */
function inline(text: string, ids: ReadonlySet<string>): string {
  // Whichever starts first wins, so a code span can hold a link's syntax and a link's text can hold a code span.
  return text
    .split(PARTS)
    .map((part) => {
      const m = LINK_WHOLE.exec(part);
      if (m) return link(m[1]!, codeSpans(m[2] ?? m[1]!), ids);
      if (part.startsWith('`') && part.endsWith('`') && part.length > 1)
        return `<code>${escapeHtml(part.slice(1, -1))}</code>`;
      // Quotes too, since a link's URL lands in an href.
      return escapeHtml(part)
        .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
        .replace(
          /\[([^\]]+)\]\(([^)\s]+)\)/g,
          (_m, shown: string, url: string) => `<a href="${href(url)}">${shown}</a>`,
        );
    })
    .join('');
}

/** A link's display text, escaped, with its code spans rendered. */
function codeSpans(text: string): string {
  return text
    .split(/(`[^`]*`)/)
    .map((p) =>
      p.startsWith('`') && p.endsWith('`') && p.length > 1
        ? `<code>${escapeHtml(p.slice(1, -1))}</code>`
        : escapeHtml(p),
    )
    .join('');
}

/** A Markdown link's URL, already escaped, once checkLink allows it. */
function href(url: string): string {
  checkLink(unescapeHtml(url, 'a link'), 'a link');
  return url;
}

/**
 * Stops the render on a link the page mustn't hold. A tree can come from anyone who sends a PR, so a scheme that can
 * run script, such as javascript:, stops it rather than reaching the page. So does a character that isn't printable,
 * since browsers drop one at the start of a URL and read the scheme after it.
 */
function checkLink(url: string, what: string): void {
  const scheme = SCHEME.exec(url);
  // Not printable as Python's str.isprintable says: a control, format or unassigned character, or a separator but space.
  const unprintable = /[\p{C}\p{Z}]/u.test(url.replaceAll(' ', ''));
  if (unprintable || (scheme && !SAFE_SCHEMES.has(scheme[0].toLowerCase()))) {
    throw new Stop(
      `trees.ts: ${what} goes to ${repr(url)}, and a page links only to relative, http(s): and mailto: URLs.`,
    );
  }
}

/** A jump to the node with the ID, showing text, which is already escaped. */
function link(slug: string, text: string, ids: ReadonlySet<string>): string {
  if (ids.has(slug)) return `<a class="jump" href="#${slug}">${text}</a>`;
  return `<span class="jump missing" title="Not in this tree">${text}</span>`;
}

function renderText(n: Node, ids: ReadonlySet<string>): string {
  const [label, rest] = labelOf(strip(n.text));
  const badge = label ? `<span class="label label-${label.toLowerCase()}">${label}</span>` : '';
  const anchors = n.id ? `<a class="anchor" href="#${n.id}" title="Link to #${n.id}">#</a>` : '';
  return `${badge}<span class="text">${inline(rest, ids)}</span>${anchors}`;
}

function renderDiagrams(n: Node): string {
  return n.diagrams
    .map((d) => {
      if (d.lang === 'mermaid') return `<pre class="mermaid" data-pending="1">${escapeHtml(d.source)}</pre>`;
      if (d.lang === 'd2') return `<div class="d2">${d2Svg(d.source, n)}</div>`;
      return `<pre class="block"><code>${escapeHtml(d.source)}</code></pre>`;
    })
    .join('');
}

function d2Svg(source: string, n: Node): string {
  const result = spawnSync('d2', D2_ARGS, { input: D2_STYLE + source, encoding: 'utf8', maxBuffer: Infinity });
  if ((result.error as NodeJS.ErrnoException | undefined)?.code === 'ENOENT') {
    throw new Stop('trees.ts: this tree has a D2 diagram, and the d2 CLI is not installed. See https://d2lang.com.');
  }
  const under = [...strip(n.text)].slice(0, 60).join('') || 'the root';
  if (result.status !== 0) throw new Stop(`trees.ts: the D2 diagram under "${under}" failed:\n${result.stderr.trim()}`);
  // Inline, so the SVG keeps D2's links and selectable text. So every href in it, which d2 writes as both href and
  // xlink:href, is held to the rule a Markdown link follows.
  const what = `a link in the D2 diagram under "${under}"`;
  for (const [, , value] of result.stdout.matchAll(/\bhref\s*=\s*(["'])(.*?)\1/g))
    checkLink(unescapeHtml(value!, what), what);
  return result.stdout.replace(/^<\?xml[^>]*\?>/, '');
}

/** The node's text as the page shows it, as plain text: its label, then its rendered text without the markup. */
function shownText(n: Node, ids: ReadonlySet<string>): string {
  const [label, rest] = labelOf(strip(n.text));
  const shown = unescapeHtml(inline(rest, ids).replace(/<[^>]+>/g, ''), 'a node');
  return label ? `${label}: ${shown}` : shown;
}

function renderNode(n: Node, ids: ReadonlySet<string>): string {
  // The node's source text, which a comment is anchored on and an agent searches the tree's file for, and the text
  // the comment editor and sidebar show a person.
  const idAttr =
    (n.id ? ` id="${n.id}"` : '') +
    ` data-src="${escapeHtml(strip(n.text))}"` +
    ` data-text="${escapeHtml(shownText(n, ids))}"`;
  const text = renderText(n, ids);
  if (!n.children.length && !n.diagrams.length) return `<li class="leaf row" tabindex="-1"${idAttr}>${text}</li>`;
  // Every node below, not just the children: the size rules keep a node's children to about 7, so that count would
  // barely vary, and the children show as soon as the branch opens.
  const below = [...nodes(n)].length - 1;
  const title = `${below} node${below === 1 ? '' : 's'} below`;
  const meta = below ? `<span class="count" title="${title}">${below}</span>` : '';
  const kids = n.children.map((c) => renderNode(c, ids)).join('');
  return (
    `<li class="branch"${idAttr}><details><summary class="row" tabindex="-1">${text}${meta}</summary>` +
    `${renderDiagrams(n)}<ul>${kids}</ul></details></li>`
  );
}

/** The page for a parsed tree, whose file is named by its path from the repo root. */
export function page(root: Root, file: string): string {
  const ids = collectIds(root, new Set());
  const values: Record<string, string> = {
    title: escapeHtml(root.title),
    intro: inline(root.intro.join(' '), ids),
    root_diagrams: renderDiagrams(root),
    tree: root.children.map((c) => renderNode(c, ids)).join(''),
    file: escapeHtml(file),
    script: SCRIPT.replace('__MERMAID__', JSON.stringify(MERMAID)),
    comments_css: COMMENTS_CSS,
    comments_script: COMMENTS_SCRIPT,
  };
  return TEMPLATE.replace(/@@(\w+)@@/g, (_m, key: string) => values[key]!);
}
