/** Path helpers that keep the Python version's results, where Node's path module differs from pathlib. */
import fs from 'node:fs';
import path from 'node:path';

/**
 * A path as pathlib writes it: no empty or `.` parts and no trailing slash, but `..` kept, since resolving it would
 * change which folder a symlink leads to. An empty path is `.`.
 */
export function pathlike(p: string): string {
  const absolute = p.startsWith('/');
  const parts = p.split('/').filter((part) => part && part !== '.');
  return (absolute ? '/' : '') + parts.join('/') || (absolute ? '/' : '.');
}

/**
 * Joins paths as pathlib's / does: a part that's absolute starts the path again, so a pack's absolute folder stays
 * itself when joined to the repo.
 */
export function pjoin(...segments: string[]): string {
  const start = segments.findLastIndex((segment) => segment.startsWith('/'));
  return path.join(...segments.slice(Math.max(start, 0)));
}

/** A path normalized as os.path.normpath does it, `..` resolved, with no trailing slash. */
export function normpath(p: string): string {
  const normal = path.normalize(p);
  return normal.length > 1 && normal.endsWith('/') ? normal.slice(0, -1) : normal;
}

/** The parts of a path, as pathlib gives them: `/` first for an absolute one, and none for `.`. */
export function parts(p: string): string[] {
  const absolute = p.startsWith('/');
  return [...(absolute ? ['/'] : []), ...p.split('/').filter((part) => part && part !== '.')];
}

/** Orders paths part by part, as pathlib sorts them, so `a/b` comes before `a-c`. */
export function byParts(a: string, b: string): number {
  const [x, y] = [parts(a), parts(b)];
  for (let i = 0; i < Math.min(x.length, y.length); i++) {
    if (x[i] !== y[i]) return x[i]! < y[i]! ? -1 : 1;
  }
  return x.length - y.length;
}

export function compare(a: string, b: string): number {
  return a < b ? -1 : a > b ? 1 : 0;
}

/** Whether path is a folder, or a symlink to one. */
export function isDir(p: string): boolean {
  return fs.statSync(p, { throwIfNoEntry: false })?.isDirectory() ?? false;
}

/** Whether path is a file, or a symlink to one. */
export function isFile(p: string): boolean {
  return fs.statSync(p, { throwIfNoEntry: false })?.isFile() ?? false;
}

export function isSymlink(p: string): boolean {
  return fs.lstatSync(p, { throwIfNoEntry: false })?.isSymbolicLink() ?? false;
}

/** Whether anything is at path, a broken symlink included, as os.path.lexists says. */
export function lexists(p: string): boolean {
  return fs.lstatSync(p, { throwIfNoEntry: false }) !== undefined;
}

/** Whether path exists, following symlinks, as Path.exists says. */
export function exists(p: string): boolean {
  return fs.statSync(p, { throwIfNoEntry: false }) !== undefined;
}

/** The absolute path with every symlink resolved, as far as the path exists, as Path.resolve gives it. */
export function resolve(p: string): string {
  const absolute = path.resolve(p);
  try {
    return fs.realpathSync(absolute);
  } catch {
    const parent = path.dirname(absolute);
    return parent === absolute ? absolute : path.join(resolve(parent), path.basename(absolute));
  }
}

/** Every path under folder, files and folders, at any depth, as Path.rglob('*') lists them, unsorted. */
export function walk(folder: string): string[] {
  return fs.readdirSync(folder, { recursive: true, encoding: 'utf8' }).map((rel) => path.join(folder, rel));
}
