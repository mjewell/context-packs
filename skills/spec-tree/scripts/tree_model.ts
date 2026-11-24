/** A spec tree read from its Markdown file: nodes with their text, ID, children and diagrams. Node's standard library only. */
import fs from 'node:fs';
import path from 'node:path';

export const LABELS = ['Why', 'Rejected'] as const;
// A node that starts with a label's word in any other form, such as `Rejected, since…` or `**Why:**`, which would show
// as plain text rather than a label.
export const BAD_LABEL = /^[*_]*(?:why|rejected)\b/i;
// A word character as Python's \w reads one: a letter or digit of any script, or _.
const W = '[\\p{L}\\p{N}_]';
const ID = new RegExp(`\\s*\\{#((?:${W}|-)+)\\}\\s*$`, 'u');
// Anything else in braces at the end of a node's text, such as `{#a #b}`, which the spec no longer allows.
const BAD_ID = /\{#[^}]*\}\s*$/;
// `[[slug]]`, or `[[slug|text]]` to show text in place of the slug.
export const LINK_SOURCE = `\\[\\[((?:${W}|-)+)(?:\\|([^\\]|]+))?\\]\\]`;
export const LINK = new RegExp(LINK_SOURCE, 'gu');

export interface Diagram {
  readonly lang: string;
  readonly lines: string[];
  readonly indent: number;
  source: string;
}

export interface Node {
  text: string;
  readonly depth: number;
  readonly children: Node[];
  readonly diagrams: Diagram[];
  id: string | null;
  file: string;
}

/** The root: its title and the sentence under it, the file, and what stops the file reading as a tree. */
export interface Root extends Node {
  title: string;
  readonly intro: string[];
  readonly problems: [string, string][];
}

function node(text: string, depth: number, file: string): Node {
  const m = ID.exec(text);
  return { text: m ? text.slice(0, m.index) : text, depth, children: [], diagrams: [], id: m ? m[1]! : null, file };
}

/** text's lines, as Python's str.splitlines gives them. */
function splitlines(text: string): string[] {
  if (!text) return [];
  const lines = text.split(/\r\n|[\n\r\v\f\x1c\x1d\x1e\x85\u2028\u2029]/);
  if (lines.at(-1) === '') lines.pop();
  return lines;
}

/** text with its leading and trailing whitespace removed, as Python's str.strip removes it. */
export function strip(text: string): string {
  return text.trim();
}

/**
 * The root (title, intro, id) and its top-level nodes. A fenced block belongs to the node above it. What stops a file
 * reading as a tree is kept in the root's `problems`, as (file, message), and the rest of it is still read.
 */
export function parse(file: string): Root {
  const root: Root = {
    ...node('', -1, file), title: path.basename(file).replace(/\.tree\.md$/, ''), intro: [], problems: [],
  };
  const stack: Node[] = [root];
  let fence: Diagram | null = null;
  for (const line of splitlines(fs.readFileSync(file, 'utf8'))) {
    const stripped = strip(line);
    if (fence !== null) {
      if (stripped.startsWith('```')) {
        stack.at(-1)!.diagrams.push(fence);
        fence = null;
      } else {
        fence.lines.push(line);
      }
      continue;
    }
    if (stripped.startsWith('```')) {
      fence = { lang: strip(stripped.slice(3)), lines: [], indent: line.length - line.trimStart().length, source: '' };
      continue;
    }
    if (!stripped || (stripped.startsWith('---') && stack.length === 1 && !root.children.length)) continue;
    if (line.startsWith('# ')) {
      const head = node(line.slice(2), -1, file);
      root.title = head.text;
      root.id = head.id;
      continue;
    }
    const m = /^( *)- (.*)$/.exec(line);
    if (!m) {
      if (!root.children.length) root.intro.push(stripped);
      continue;
    }
    const depth = Math.floor(m[1]!.length / 2);
    while (stack.at(-1)!.depth >= depth) stack.pop();
    const child = node(m[2]!, depth, file);
    if (!child.id && BAD_ID.test(child.text)) {
      root.problems.push([file, `a node has one ID, written {#slug}, under "${where(child)}"`]);
    }
    stack.at(-1)!.children.push(child);
    stack.push(child);
  }
  for (const d of allDiagrams(root)) d.source = d.lines.map((l) => l.slice(d.indent)).join('\n');
  return root;
}

function* allDiagrams(n: Node): Generator<Diagram> {
  yield* n.diagrams;
  for (const child of n.children) yield* allDiagrams(child);
}

export function labelOf(text: string): [string | null, string] {
  for (const label of LABELS) {
    if (text.startsWith(`${label}:`)) return [label, strip(text.slice(label.length + 1))];
  }
  return [null, text];
}

/** The ID each link in the text points at. */
export function slugs(text: string): string[] {
  return [...text.matchAll(LINK)].map((m) => m[1]!);
}

export function collectIds(n: Node, out: Set<string>): Set<string> {
  if (n.id) out.add(n.id);
  for (const child of n.children) collectIds(child, out);
  return out;
}

/** The node and every node below it, in reading order. */
export function* nodes(n: Node): Generator<Node> {
  yield n;
  for (const child of n.children) yield* nodes(child);
}

function isRoot(n: Node): n is Root {
  return 'intro' in n;
}

/** A node's text, short enough to name it in a message. The root is named by its title. */
export function where(n: Node): string {
  const text = strip(n.text) || (isRoot(n) ? n.title : '');
  const characters = [...text];
  return characters.length <= 50 ? text : `${characters.slice(0, 49).join('')}…`;
}

/**
 * Words in a node's text, as the spec counts them: labels, IDs, link slugs and code spans don't count, and a link's
 * display text does.
 */
export function words(text: string): number {
  let t = strip(text).replace(/^(Why|Rejected):/, ' ');
  t = t.replace(LINK, (_m, _slug, shown?: string) => ` ${shown ?? ''} `).replace(/`[^`]*`/g, ' ');
  t = t.replace(/\[([^\]]*)\]\([^)]*\)/g, '$1');
  return t.replace(/[*_]/g, ' ').split(/\s+/).filter((w) => w && new RegExp(W, 'u').test(w)).length;
}

/** Words in what a node shows: its text, or for the root, the sentence under its title. */
export function ownWords(n: Node): number {
  return isRoot(n) ? words(n.intro.join(' ')) : words(n.text);
}
