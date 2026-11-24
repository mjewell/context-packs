/** The checks ../spec.md gives CI: what breaks a tree fails, and sizes warn until they're far off. Node's standard library only. */
import fs from 'node:fs';
import path from 'node:path';

import { BAD_LABEL, type Node, type Root, labelOf, nodes, ownWords, parse, slugs, strip, where } from './tree_model.ts';

// The spec's targets. A size past its target warns, and past 1.5 times it fails.
const NODE_WORDS = 40;
const CHILDREN = 7;
const VIEW_WORDS = 150;
// A nested subtree this small only warns: it's a sign to flatten it.
const FLATTEN_WORDS = 60;

export type Problem = [string, 'fail' | 'warn', string];

function compare(a: string, b: string): number {
  return a < b ? -1 : a > b ? 1 : 0;
}

/** Orders paths part by part, as Python sorts them, so `a/b` comes before `a-c`. */
export function byParts(a: string, b: string): number {
  const [x, y] = [a.split('/'), b.split('/')];
  for (let i = 0; i < Math.min(x.length, y.length); i++) if (x[i] !== y[i]) return compare(x[i]!, y[i]!);
  return x.length - y.length;
}

/** Each tree's file, `<id>.tree.md`, anywhere in the repo outside dot-folders, in the order os.walk visits them. */
function treeRoots(repo: string): string[] {
  const roots: string[] = [];
  const visit = (folder: string): void => {
    const entries = fs.readdirSync(folder, { withFileTypes: true });
    roots.push(...entries.filter((e) => !e.isDirectory() && e.name.endsWith('.tree.md')).map((e) => e.name).sort(compare)
      .map((name) => path.join(folder, name)));
    for (const dir of entries.filter((e) => e.isDirectory() && !e.name.startsWith('.')).map((e) => e.name).sort(compare)) {
      visit(path.join(folder, dir));
    }
  };
  visit(repo);
  return roots;
}

/** Every problem in the repo's trees, as (file, level, message), with level 'fail' or 'warn'. */
export function check(repo: string): Problem[] {
  const trees = treeRoots(repo).map(parse);
  const problems: Problem[] = trees.flatMap((tree) => tree.problems.map(([file, message]): Problem => [file, 'fail', message]));
  const byId = new Map<string, Node[]>();
  const withIds = trees.flatMap((tree) => [...nodes(tree)].filter((n) => n.id)).sort((a, b) => byParts(a.file, b.file));
  for (const n of withIds) byId.set(n.id!, [...(byId.get(n.id!) ?? []), n]);
  for (const [first, ...others] of byId.values()) {
    for (const n of others) {
      problems.push([n.file, 'fail', `{#${n.id}} is also the ID of a node in ${path.relative(repo, first!.file)}`]);
    }
  }
  for (const tree of trees) {
    for (const n of nodes(tree)) {
      for (const slug of slugs(n.text)) {
        if (!byId.has(slug)) problems.push([n.file, 'fail', `[[${slug}]] doesn't resolve, under "${where(n)}"`]);
      }
    }
  }
  for (const tree of trees) {
    for (const n of nodes(tree)) {
      const text = strip(n.text);
      if (n.depth >= 0 && !labelOf(text)[0] && BAD_LABEL.test(text)) {
        problems.push([n.file, 'fail', `a label is written Why: or Rejected:, under "${where(n)}"`]);
      }
      problems.push(...sized(n.file, (size) => `node text is ${size} words`, ownWords(n), NODE_WORDS, where(n)));
      problems.push(...sized(n.file, (size) => `has ${size} children`, n.children.length, CHILDREN, where(n)));
      const view = ownWords(n) + n.children.reduce((sum, child) => sum + ownWords(child), 0);
      if (n.children.length) problems.push(...sized(n.file, (size) => `view is ${size} words`, view, VIEW_WORDS, where(n)));
      const size = subtreeWords(n);
      if (n.children.some((child) => child.children.length) && size <= FLATTEN_WORDS) {
        problems.push([n.file, 'warn', `nested subtree is ${size} words (flatten at ${FLATTEN_WORDS} or `
                                       + `fewer), under "${where(n)}"`]);
      }
    }
  }
  return problems;
}

function subtreeWords(n: Node): number {
  return ownWords(n) + n.children.reduce((sum, child) => sum + subtreeWords(child), 0);
}

/** A warning when size passes its target, or a failure past 1.5 times it. */
function sized(file: string, what: (size: number) => string, size: number, target: number, under?: string): Problem[] {
  const limit = Math.floor(target * 3 / 2);
  const at = under ? `, under "${under}"` : '';
  if (size > limit) return [[file, 'fail', `${what(size)} (limit ${limit})${at}`]];
  if (size > target) return [[file, 'warn', `${what(size)} (target ${target})${at}`]];
  return [];
}

/** Lines giving each view's size, child count and subtree size, indented by depth. */
export function stats(repo: string): string[] {
  const lines: string[] = [];
  for (const tree of treeRoots(repo).map(parse)) {
    for (const n of nodes(tree)) {
      if (!n.children.length) continue;
      const count = n.children.length;
      const view = ownWords(n) + n.children.reduce((sum, child) => sum + ownWords(child), 0);
      lines.push(`${'  '.repeat(n.depth + 1)}${where(n)}: view ${view}, ${count} `
                 + `${count === 1 ? 'child' : 'children'}, subtree ${subtreeWords(n)}`);
    }
  }
  return lines;
}

/** Each node that links to the ID, as (file, text), in path order. null when no node has the ID. */
export function linksTo(repo: string, slug: string): [string, string][] | null {
  const every = treeRoots(repo).map(parse).flatMap((tree: Root) => [...nodes(tree)]);
  if (!every.some((n) => n.id === slug)) return null;
  return every.filter((n) => slugs(n.text).includes(slug)).map((n): [string, string] => [n.file, strip(n.text)])
    .sort((a, b) => byParts(a[0], b[0]) || compare(a[1], b[1]));
}
