/** Context packs: where each comes from, and its content once fetched. */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import * as origins from './origins.ts';
import { exists, isDir, normpath, parts, pjoin, resolve } from './paths.ts';
import { fail, type Stack } from './stop.ts';

// The folder holding a repo's packs, which renders into its context-packs block, and the folder inside it the sync
// writes into.
export const ROOT = 'context-packs';
export const GEN = 'context-packs/gen';
// A git URL, as git tells one from a path: it has a scheme, such as https:// or file://, or is scp-like, such as
// git@github.com:acme/rules.git, with a colon before any slash.
const GIT_URL = /^(?:[A-Za-z][A-Za-z0-9+.-]*:\/\/|[^/]+:)/;

/** The folder at path in origin, normalized. */
export function folder(origin: string, p: string): string {
  return normpath(pjoin(origin, p));
}

/**
 * Whether origin is a folder on disk rather than a git URL: any path, such as . for the synced repo itself or
 * ../agent-config beside it, or absolute. A local pack syncs from its working tree.
 */
export function local(origin: string): boolean {
  return !GIT_URL.test(origin);
}

/**
 * Where a pack comes from: a folder in a git repo pinned to a ref, or a folder on disk, relative to the synced repo.
 * id is the folder under context-packs/ it renders at, '' for context-packs/ itself.
 */
export interface Pack {
  readonly id: string;
  readonly origin: string;
  readonly path: string;
  readonly ref: string | null;
}

export function same(a: Pack, b: Pack): boolean {
  return a.id === b.id && a.origin === b.origin && a.path === b.path && a.ref === b.ref;
}

export function isLocal(pack: Pack): boolean {
  return local(pack.origin);
}

/** The folder the sync writes the pack's files into, relative to the synced repo. */
export function generated(pack: Pack): string {
  return path.join(GEN, pack.id);
}

/**
 * Where the pack's docs sit, relative to the synced repo: copied into its generated folder, or where they are for a
 * local pack.
 */
export function synced(pack: Pack): string {
  return isLocal(pack) ? folder(pack.origin, pack.path) : generated(pack);
}

/** A file or folder in the pack, as an error names it. */
export function where(pack: Pack, rel = ''): string {
  if (isLocal(pack)) return pjoin(synced(pack), rel);
  return `${path.posix.join(pack.path || '.', rel)} in ${pack.origin}`;
}

export const REPO: Pack = { id: '', origin: '.', path: ROOT, ref: null };

/**
 * Where the paths in the synced folder's tables start from: its path from the root of the git repo holding it, where
 * sessions start, else its absolute path, since a session above the repos or in a user's config can start anywhere.
 */
export function base(repo: string): string {
  const resolved = resolve(repo);
  for (let folder = resolved; ; folder = path.dirname(folder)) {
    if (exists(path.join(folder, '.git'))) return path.relative(folder, resolved) || '.';
    if (folder === path.dirname(folder)) return resolved;
  }
}

/** Where the pack's content is, as an origin and the parts of a folder in it, to tell when two packs overlap. */
export type Place = readonly [string, readonly string[]];

export function place(repo: string, pack: Pack): Place {
  if (isLocal(pack)) return ['', parts(normpath(pjoin(repo, synced(pack))))];
  return [pack.origin, parts(path.posix.normalize(pack.path || '.'))];
}

export function samePlace(a: Place, b: Place): boolean {
  return a[0] === b[0] && a[1].length === b[1].length && a[1].every((part, i) => part === b[1][i]);
}

/** Whether one of two places holds the other. */
export function overlap(a: Place, b: Place): boolean {
  const [[origin, outer], [other, inner]] = [a, b].sort((x, y) => x[1].length - y[1].length) as [Place, Place];
  return origin === other && outer.every((part, i) => inner[i] === part);
}

/** The folder holding pack's content, fetched at its ref unless it's local. */
export function fetch(repo: string, pack: Pack, stack: Stack): string {
  if (isLocal(pack)) {
    const content = pjoin(repo, synced(pack));
    if (!isDir(content)) {
      fail(`context-packs: the ${pack.id} pack's folder, ${synced(pack)}, isn't there, relative to ${repo}.`);
    }
    return content;
  }
  const into = fs.mkdtempSync(path.join(os.tmpdir(), 'context-packs-'));
  stack.defer(() => fs.rmSync(into, { recursive: true, force: true }));
  return origins.extract(pack.origin, pack.ref!, pack.path, into);
}
