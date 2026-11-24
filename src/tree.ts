/**
 * The packs in context-packs/ as a tree: the repo's own pack.md and docs, each folder holding a pack.md of its own
 * nested inside, and each import pack replaced by the pack it names. A folder without a pack.md only groups files,
 * whose docs join the nearest pack's table.
 */
import fs from 'node:fs';
import path from 'node:path';

import {
  fetch,
  folder,
  generated,
  isLocal,
  local,
  overlap,
  type Pack,
  type Place,
  place,
  REPO,
  same,
  samePlace,
  synced,
  where,
} from './packs.ts';
import { byParts, compare, isDir, isFile, normpath, pjoin } from './paths.ts';
import { fail, type Stack } from './stop.ts';

export const FRONT = /^---\n([\s\S]*?)\n---\n/;
// An import pack's front matter: its when, which replaces the imported pack's, and where that pack comes from.
export const IMPORT_KEYS = ['when', 'from', 'path', 'ref'] as const;

type Fields = Record<string, string>;

export interface Doc {
  readonly path: string;
  readonly when: string;
}

/**
 * A pack in the tree. Its id is its folder relative to the folder its content was read from, '' for the pack at the
 * top, and paths are relative to that folder too. Its files are every one it brings, docs included, but not those of
 * the packs nested in it.
 */
export interface Node {
  readonly id: string;
  readonly fields: Fields;
  readonly rules: string;
  readonly docs: readonly Doc[];
  readonly files: readonly string[];
  readonly children: readonly Node[];
  readonly imports: readonly Imported[];
}

/**
 * The pack an import pack names, at the import pack's folder in the pack holding it: its root carries the import
 * pack's when and rules ahead of its own, and source is the folder holding its content.
 */
export interface Imported {
  readonly id: string;
  readonly pack: Pack;
  readonly root: Node;
  readonly source: string;
}

/**
 * Whether the pack gets a row pointing at its index, rather than having its pack rules and table inlined after the
 * rules and table of the pack holding it: it does when it has a when other than always.
 */
export function row(node: Node): boolean {
  return (node.fields.when ?? 'always') !== 'always';
}

/** Every pack nested in this one, at any depth, parents before their children. */
export function* nested(node: Node): Generator<Node> {
  for (const child of node.children) {
    yield child;
    yield* nested(child);
  }
}

/** Whether a pack.md's front matter names a pack to import: another repo's, or a folder of its own repo's. */
export function importsAPack(text: string): boolean {
  const match = FRONT.exec(text);
  return !!match && match[1]!.split('\n').some((line) => line.startsWith('from: ') || line.startsWith('path: '));
}

/** text's front matter as fields, keeping only those named in keys, and the text after it. */
export function front(text: string, at: string, keys: readonly string[]): [Fields, string] {
  const match = FRONT.exec(text);
  const pairs = match
    ? match[1]!.split('\n').map((line) => {
        const colon = line.indexOf(': ');
        return colon === -1 ? [line] : [line.slice(0, colon), line.slice(colon + 2)];
      })
    : [];
  const fields: Fields = Object.fromEntries(pairs.filter((pair) => pair.length === 2));
  if (Object.keys(fields).length !== pairs.length) {
    fail(`context-packs: ${at} has front matter that isn't \`key: value\` lines.`);
  }
  const names = Object.keys(fields).sort(compare);
  if (names.length && !keys.length) {
    fail(
      `context-packs: ${at} takes no front matter, since its pack rules are always inlined. ` +
        `Remove ${names.join(', ')}.`,
    );
  }
  const unknown = names.filter((name) => !keys.includes(name));
  if (unknown.length) {
    fail(
      `context-packs: ${at} has front matter context-packs doesn't know: ${unknown.join(', ')}. ` +
        `It takes only ${keys.map((k) => `\`${k}\``).join(', ')}. Remove it, or update context-packs if the ` +
        'pack needs a newer version.',
    );
  }
  return [fields, match ? text.slice(match[0].length) : text];
}

export function read(file: string): string {
  return fs.readFileSync(file, 'utf8');
}

/** The names in folder, sorted, as Path.iterdir sorted gives them. */
function entries(folderPath: string): string[] {
  return fs.readdirSync(folderPath).sort(compare);
}

/**
 * The tree of context-packs/ in repo, with each pack it imports fetched into a folder stack cleans up. Stops when two
 * packs overlap, which also catches a pack importing a folder that holds it. A folder imported in two places, such as
 * one two packs from the same repo both include, renders in each, at each one's ref.
 */
export function load(repo: string, stack: Stack): Node {
  // Every pack loaded so far, and the ones being loaded: the pack claiming a folder and those holding it.
  const claimed: [Pack, Place][] = [];
  const loading: Pack[] = [];

  function claim(pack: Pack): void {
    const here = place(repo, pack);
    for (const [other, there] of claimed) {
      const shared = samePlace(here, there) && !loading.some((p) => same(p, other));
      if (overlap(here, there) && !shared) {
        fail(
          `context-packs: the ${other.id || 'context-packs'} and ${pack.id} packs overlap: one's ` +
            "folder holds the other's, so its rules would sync twice. Keep only one of them.",
        );
      }
    }
    claimed.push([pack, here]);
  }

  /** The pack the import pack at rel in holder names, holder's source holding holder's content. */
  function imported(holder: Pack, source: string, rel: string): Imported {
    const at = where(holder, path.join(rel, 'pack.md'));
    const others = entries(path.join(source, rel)).filter((name) => name !== 'pack.md' && !name.startsWith('.'));
    if (others.length) {
      fail(
        `context-packs: ${where(holder, rel)} is an import pack, so it holds only its pack.md. Move ` +
          `${others.join(', ')} beside it.`,
      );
    }
    let [fields, rules] = front(read(path.join(source, rel, 'pack.md')), at, IMPORT_KEYS);
    const id = [holder.id, rel].filter(Boolean).join('/');
    // from names another repo, and without it the path is a folder of the repo the import pack is in: the synced repo
    // for context-packs/, or the repo of the pack from elsewhere holding it.
    const origin = fields.from;
    let folderPath = folder('.', fields.path ?? '');
    if (folderPath === '..' || folderPath.startsWith('../') || folderPath.startsWith('/')) {
      fail(
        `context-packs: ${at} imports ${folderPath}, which is outside the repo ` +
          `${origin ? 'its from names' : 'it is in'}. Name the other repo in \`from\`, and the folder in ` +
          'it in `path`.',
      );
    }
    folderPath = folderPath === '.' ? '' : folderPath;
    if (origin && !isLocal(holder)) {
      fail(
        `context-packs: ${at} imports ${origin}, but it sits in a pack from git, which can import only ` +
          'folders of its own repo, with `path` alone.',
      );
    }
    if ((!origin || local(origin)) && 'ref' in fields) {
      fail(
        `context-packs: ${at} pins a folder on disk to a ref, but a folder on disk is read from its ` +
          "working tree, and a folder of the pack's own repo moves with that pack. Remove the ref line, " +
          'or import the pack by its git URL to pin it.',
      );
    }
    let pack: Pack;
    if (!origin) {
      pack = { id, origin: holder.origin, path: folderPath, ref: holder.ref };
    } else if (local(origin)) {
      pack = { id, origin: folder(holder.origin, origin), path: folderPath, ref: null };
    } else {
      if (!('ref' in fields)) {
        fail(
          `context-packs: ${at} imports ${origin} without a ref to pin it to. Add \`ref: <tag or ` +
            'commit>`, or delete the folder and add the pack again.',
        );
      }
      pack = { id, origin, path: folderPath, ref: fields.ref! };
    }
    claim(pack);
    const content = fetch(repo, pack, stack);
    loading.push(pack);
    let root = tree(pack, content, '', ['when']);
    loading.pop();
    if (rules && !rules.endsWith('\n')) rules += '\n';
    root = {
      ...root,
      fields: { ...root.fields, ...(fields.when === undefined ? {} : { when: fields.when }) },
      rules: [rules, root.rules].filter(Boolean).join('\n'),
    };
    return { id: rel, pack, root, source: content };
  }

  /** The pack at the folder id in source, which holds pack's content, and the packs nested in it. */
  function tree(pack: Pack, source: string, id: string, keys: readonly string[]): Node {
    const home = id || '.';
    const packMd = path.join(source, home, 'pack.md');
    let [fields, rules]: [Fields, string] = isFile(packMd)
      ? front(read(packMd), where(pack, path.join(home, 'pack.md')), keys)
      : [{}, ''];
    // A nested pack's when is its row in its parent's table. The top-level pack needs none: without one, it's
    // inlined.
    if (id && !('when' in fields)) {
      fail(
        `context-packs: ${where(pack, path.join(home, 'pack.md'))} must start with front matter saying when to ` +
          "read it, since it's nested in another pack:\n\n---\nwhen: Editing `web/**`\n---",
      );
    }
    // The end marker has to start its own line, or the next sync can't find the block.
    if (rules && !rules.endsWith('\n')) rules += '\n';
    const docs: Doc[] = [];
    const files: string[] = [];
    const children: Node[] = [];
    const imports: Imported[] = [];

    function walk(rel: string): void {
      for (const name of entries(path.join(source, rel))) {
        const entryPath = path.join(rel, name);
        const entry = path.join(source, entryPath);
        if (name.startsWith('.') || entryPath === path.join(home, 'pack.md') || (!pack.id && entryPath === 'gen')) {
          continue;
        }
        if (isDir(entry) && isFile(path.join(entry, 'pack.md'))) {
          if (importsAPack(read(path.join(entry, 'pack.md')))) {
            imports.push(imported(pack, source, entryPath));
            continue;
          }
          const twin = path.join(path.dirname(entryPath), `${name}.md`);
          if (isFile(path.join(source, twin))) {
            fail(
              `context-packs: ${where(pack, entryPath)} holds a pack.md and sits beside ` +
                `${where(pack, twin)}, so its index and that doc would both be ${twin}. Rename one.`,
            );
          }
          children.push(tree(pack, source, entryPath, ['when']));
        } else if (isDir(entry)) {
          walk(entryPath);
        } else {
          files.push(entryPath);
          if (path.extname(name) === '.md') docs.push({ path: entryPath, when: when(pack, entryPath, read(entry)) });
        }
      }
    }

    if (isDir(path.join(source, home))) walk(home);
    return { id, fields, rules, docs, files, children, imports };
  }

  claim(REPO);
  loading.push(REPO);
  return tree(REPO, pjoin(repo, synced(REPO)), '', []);
}

/** The when of the doc at path in pack, whose text is text. */
function when(pack: Pack, docPath: string, text: string): string {
  const [fields] = front(text, where(pack, docPath), ['when']);
  if (!('when' in fields)) {
    fail(
      `context-packs: ${where(pack, docPath)} must start with front matter saying when to read it:\n\n` +
        '---\nwhen: Editing `**/*.ts`\n---',
    );
  }
  if (fields.when === 'always') {
    fail(
      `context-packs: ${where(pack, docPath)} has \`when: always\`, but only a pack.md is inlined. Move its ` +
        'rules into the pack.md of the pack holding it, or give it a when saying when to read it.',
    );
  }
  return fields.when!;
}

/** Where a pack's generated index sits: pack.md for the top-level pack, since no doc can have that name. */
function index(node: Node, pack: Pack): string {
  return path.join(generated(pack), `${node.id || 'pack'}.md`);
}

/** A table of (when, path) rows under its heading, or nothing without rows, each path starting from base. */
function table(heading: string, rows: [string, string][], base: string): string {
  if (!rows.length) return '';
  return (
    `${heading}\n\n| When | Read |\n|---|---|\n` +
    rows.map(([when, rowPath]) => `| ${when} | \`${normpath(pjoin(base, rowPath))}\` |\n`).join('')
  );
}

/** The pack's folder under context-packs/, '' for context-packs/ itself. */
function name(node: Node, pack: Pack): string {
  return [pack.id, node.id].filter(Boolean).join('/');
}

function heading(node: Node, pack: Pack): string {
  return name(node, pack) ? `## ${name(node, pack)} context` : '## Context';
}

/**
 * The pack rendered where its parent's rules and table end, between markers naming it, which only show people
 * reading the file where each pack starts and ends.
 */
function inline(node: Node, pack: Pack, base: string): string {
  return (
    `<!-- context-packs:pack ${name(node, pack)} -->\n${render(node, pack, base)}` +
    `<!-- context-packs:pack-end ${name(node, pack)} -->\n`
  );
}

/**
 * The node's rules, then its table: a row for each of its docs, and for each pack nested in it or imported into it
 * that gets one, its path starting from base. Each of those packs that doesn't is rendered the same way after it.
 */
export function render(node: Node, pack: Pack, base: string): string {
  const rows: [string, string, string][] = [
    ...node.docs.map((d): [string, string, string] => [
      d.path.slice(0, -'.md'.length),
      d.when,
      pjoin(synced(pack), d.path),
    ]),
    ...node.children.filter(row).map((c): [string, string, string] => [c.id, c.fields.when!, index(c, pack)]),
    ...node.imports
      .filter((i) => row(i.root))
      .map((i): [string, string, string] => [i.id, i.root.fields.when!, index(i.root, i.pack)]),
  ].sort((a, b) => compare(a[0], b[0]) || compare(a[1], b[1]) || byParts(a[2], b[2]));
  const inlined = [
    ...node.children.filter((c) => !row(c)).map((c) => inline(c, pack, base)),
    ...node.imports.filter((i) => !row(i.root)).map((i) => inline(i.root, i.pack, base)),
  ];
  return [
    node.rules,
    table(
      heading(node, pack),
      rows.map(([, when, rowPath]) => [when, rowPath]),
      base,
    ),
    ...inlined,
  ]
    .filter(Boolean)
    .join('\n');
}

/**
 * Copy the packs' files from source into repo, unless the pack is local, and write the index of each pack that gets a
 * row, then do the same for each pack imported into them.
 */
export function write(root: Node, pack: Pack, source: string, repo: string, base: string): void {
  for (const node of [root, ...nested(root)]) {
    for (const file of isLocal(pack) ? [] : node.files) {
      const target = path.join(repo, synced(pack), file);
      fs.mkdirSync(path.dirname(target), { recursive: true });
      fs.cpSync(path.join(source, file), target, { dereference: true, preserveTimestamps: true });
    }
    if (row(node)) {
      const target = path.join(repo, index(node, pack));
      fs.mkdirSync(path.dirname(target), { recursive: true });
      fs.writeFileSync(target, render(node, pack, base), 'utf8');
    }
    for (const imported of node.imports) write(imported.root, imported.pack, imported.source, repo, base);
  }
}
