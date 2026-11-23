/** Fetch context packs from their git origins, through a cache of bare clones that every sync shares. */
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { exists } from './paths.ts';
import { fail } from './stop.ts';

export const COMMIT = /^[0-9a-f]{40}$/;

function run(args: string[], input?: Buffer) {
  return spawnSync('git', args, { input, maxBuffer: Infinity });
}

function git(...args: string[]): string {
  const result = run(args);
  if (result.status !== 0) {
    fail(`context-packs: git ${args.join(' ')} failed:\n${String(result.stderr ?? result.error).trim()}`);
  }
  return result.stdout.toString().trim();
}

/** The cached bare clone of url, cloning it the first time. */
function clone(url: string): string {
  const cache = path.join(process.env.XDG_CACHE_HOME || path.join(os.homedir(), '.cache'), 'context-packs');
  const folder = path.join(cache, url.replace(/[^A-Za-z0-9._-]+/g, '_'));
  if (!exists(folder)) {
    fs.mkdirSync(cache, { recursive: true });
    git('clone', '--quiet', '--bare', url, folder);
  }
  return folder;
}

/** The full commit ref names in the clone at folder, or null if it names none. */
function commit(folder: string, ref: string): string | null {
  const result = run(['--git-dir', folder, 'rev-parse', '--verify', '--quiet', `${ref}^{commit}`]);
  return result.status === 0 ? result.stdout.toString().trim() : null;
}

/** The cached clone of url, fetched until it has ref, or null if the origin has no such commit or tag. */
function fetched(url: string, ref: string): string | null {
  const folder = clone(url);
  if (!commit(folder, ref)) {
    git('--git-dir', folder, 'fetch', '--quiet', 'origin', '+refs/heads/*:refs/heads/*', '+refs/tags/*:refs/tags/*');
  }
  return commit(folder, ref) ? folder : null;
}

/** url's tags or branches, by name. */
function remote(url: string, kind: 'tags' | 'heads'): Map<string, string> {
  const lines = git('ls-remote', `--${kind}`, '--refs', url).split('\n').filter(Boolean);
  return new Map(lines.map((line) => {
    const [sha, ref] = line.split('\t') as [string, string];
    return [ref.split('/').slice(2).join('/'), sha];
  }));
}

/** The commit at the tip of url's default branch. */
export function tip(url: string): string {
  const head = git('ls-remote', url, 'HEAD').split(/\s+/).filter(Boolean);
  if (!head.length) fail(`context-packs: ${url} has no default branch to pin to.`);
  return head[0]!;
}

/** ref as a pack's marker holds it: a tag stays a tag, and a commit becomes its full hash. */
export function pin(url: string, ref: string): string {
  if (remote(url, 'tags').has(ref)) return ref;
  if (remote(url, 'heads').has(ref)) {
    fail(`context-packs: ${ref} is a branch in ${url}, and a branch moves. Pin to a tag or a commit, `
         + 'or leave out --ref to follow the default branch on update.');
  }
  const folder = fetched(url, ref);
  if (!folder) fail(`context-packs: ${url} has no tag or commit ${ref}.`);
  return commit(folder, ref)!;
}

/** Where an update moves a pack pinned to ref: a commit to the tip of the default branch, and a tag nowhere. */
export function latest(url: string, ref: string): string {
  return COMMIT.test(ref) ? tip(url) : ref;
}

/** Write the folder at path in url, as of ref, into the folder into, and return where it landed. */
export function extract(url: string, ref: string, folderPath: string, into: string): string {
  const folder = fetched(url, ref);
  if (!folder) {
    fail(`context-packs: ${url} has no tag or commit ${ref}. Pin the pack to one that exists, then sync again.`);
  }
  const archive = run(['--git-dir', folder, 'archive', '--format=tar', ref, '--', folderPath || '.']);
  if (archive.status !== 0) {
    fail(`context-packs: ${url} has no folder ${folderPath} at ${ref}:\n${archive.stderr.toString().trim()}`);
  }
  // Node has no tar reader, and every machine git runs on has tar.
  const unpacked = spawnSync('tar', ['-x', '-C', into], { input: archive.stdout, maxBuffer: Infinity });
  if (unpacked.status !== 0) {
    fail(`context-packs: couldn't unpack ${url} at ${ref}:\n${String(unpacked.stderr ?? unpacked.error).trim()}`);
  }
  return path.join(into, folderPath);
}
