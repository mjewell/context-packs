/**
 * The import packs in context-packs/: folders whose pack.md names a pack from elsewhere, which syncs in their place.
 * The commands add, remove and move the pins of these; the ones that packs from elsewhere hold are theirs to change.
 */
import fs from 'node:fs';
import path from 'node:path';

import type { Args } from './args.ts';
import * as origins from './origins.ts';
import { local, ROOT } from './packs.ts';
import { byParts, exists, isDir, parts, walk } from './paths.ts';
import { fail } from './stop.ts';
import * as tree from './tree.ts';

const REF = /^ref: .*$/m;
// A folder under context-packs/: names of letters, digits, dots, dashes and underscores, none starting with a dot.
const ID = /^[A-Za-z0-9_-][A-Za-z0-9._-]*(?:\/[A-Za-z0-9_-][A-Za-z0-9._-]*)*$/;

/**
 * An import pack in context-packs/: its folder there, its pack.md relative to the synced repo and that file's text,
 * and where the pack it names comes from.
 */
export interface Import {
  readonly id: string;
  readonly file: string;
  readonly text: string;
  readonly origin: string;
  readonly path: string;
  readonly ref: string | null;
}

/** The import packs in context-packs/, by the order of their folders. */
export function scan(repo: string): Import[] {
  const root = path.join(repo, ROOT);
  if (!isDir(root)) return [];
  const found: Import[] = [];
  const packMds = walk(root)
    .filter((file) => path.basename(file) === 'pack.md')
    .sort(byParts);
  for (const packMd of packMds) {
    const rel = path.relative(root, packMd);
    const relParts = parts(rel);
    // context-packs/pack.md is the repo's own rules, never an import pack.
    if (relParts.length === 1 || relParts[0] === 'gen' || relParts.some((p) => p.startsWith('.'))) continue;
    const text = tree.read(packMd);
    if (tree.importsAPack(text)) {
      const file = path.join(ROOT, rel);
      const [fields] = tree.front(text, file, tree.IMPORT_KEYS);
      found.push({
        id: path.dirname(rel),
        file,
        text,
        origin: fields.from ?? '.',
        path: fields.path ?? '',
        ref: fields.ref ?? null,
      });
    }
  }
  return found;
}

/** A file the command writes, relative to the repo, with null for text deleting the import pack's folder. */
export type Edit = readonly [string, string | null];

/** The files the command writes, given the import packs there before it runs. */
export function command(args: Args, repo: string, imports: readonly Import[]): Edit[] {
  const ids = imports.map((i) => i.id);
  if (args.command === 'add') {
    if (!ID.test(args.id) || args.id.split('/')[0] === 'gen') {
      fail(
        `context-packs: ${args.id} can't name a pack. Use a folder under ${ROOT}/, other than ` +
          'gen/, named with letters, digits, dots, dashes and underscores, not starting with a dot.',
      );
    }
    const target = path.join(ROOT, args.id);
    if (exists(path.join(repo, target)))
      fail(`context-packs: ${target} already exists. Choose another id, or remove it.`);
    if (local(args.origin) && args.ref) {
      fail(
        `context-packs: ${args.origin} is a folder on disk, which syncs from its working tree, so ` +
          'it takes no --ref.',
      );
    }
    let [origin, folderPath, ref]: [string | null, string, string | null] = [args.origin, args.path, null];
    if (local(args.origin)) {
      const inside = path.relative(path.resolve(repo), path.resolve(repo, args.origin, args.path)) || '.';
      // A folder of the synced repo is named by its path alone, so it reads the same however add was given it.
      if (inside !== '..' && !inside.startsWith(`..${path.sep}`)) [origin, folderPath] = [null, inside];
    } else {
      ref = args.ref ? origins.pin(args.origin, args.ref) : origins.tip(args.origin);
    }
    const text =
      '---\n' +
      (args.when ? `when: ${args.when}\n` : '') +
      (origin ? `from: ${origin}\n` : '') +
      (folderPath ? `path: ${folderPath}\n` : '') +
      (ref ? `ref: ${ref}\n` : '') +
      '---\n';
    return [[path.join(target, 'pack.md'), text]];
  }
  const named = args.command === 'remove' ? [args.id] : args.command === 'update' ? args.ids : [];
  const unknown = named.filter((n) => !ids.includes(n));
  if (unknown.length) {
    fail(
      `context-packs: ${args.dir} has no import pack ${unknown.join(', ')} in ${ROOT}/. ` +
        `Its import packs: ${ids.join(', ') || 'none'}.`,
    );
  }
  if (args.command === 'remove') return imports.filter((i) => i.id === args.id).map((i) => [i.file, null]);
  if (args.command !== 'update') return [];
  if (args.ref && named.length !== 1) fail('context-packs: --ref pins one pack, so name exactly one.');
  const edits: Edit[] = [];
  for (const imported of imports) {
    if (named.length && !named.includes(imported.id)) continue;
    if (local(imported.origin)) {
      if (args.ref) {
        fail(
          `context-packs: the ${imported.id} pack syncs from the working tree of ${imported.origin}, ` +
            'so it takes no --ref.',
        );
      }
      continue;
    }
    const ref = args.ref ? origins.pin(imported.origin, args.ref) : origins.latest(imported.origin, imported.ref!);
    if (ref !== imported.ref) edits.push([imported.file, imported.text.replace(REF, () => `ref: ${ref}`)]);
  }
  return edits;
}

/** Write the edits, run body, and put everything back if the sync stops before it's done. */
export async function applied<T>(repo: string, edits: readonly Edit[], body: () => Promise<T>): Promise<T> {
  const undo: (() => void)[] = [];
  try {
    for (const [file, text] of edits) {
      const packMd = path.join(repo, file);
      if (text === null) {
        const old = tree.read(packMd);
        fs.rmSync(path.dirname(packMd), { recursive: true });
        undo.push(() => {
          fs.mkdirSync(path.dirname(packMd), { recursive: true });
          fs.writeFileSync(packMd, old, 'utf8');
        });
        continue;
      }
      const created = ancestors(packMd).find((folder) => !exists(folder));
      if (created) {
        fs.mkdirSync(path.dirname(packMd), { recursive: true });
        undo.push(() => fs.rmSync(created, { recursive: true, force: true }));
      } else {
        const old = tree.read(packMd);
        undo.push(() => fs.writeFileSync(packMd, old, 'utf8'));
      }
      fs.writeFileSync(packMd, text, 'utf8');
    }
    return await body();
  } catch (error) {
    for (const step of undo.reverse()) step();
    throw error;
  }
}

/** The folders holding file, outermost first, as reversed(Path.parents) lists them. */
function ancestors(file: string): string[] {
  const found: string[] = [];
  for (let folder = path.dirname(file); ; folder = path.dirname(folder)) {
    found.unshift(folder);
    if (folder === path.dirname(folder)) return found;
  }
}
