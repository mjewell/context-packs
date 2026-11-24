/**
 * A commit made from the working files, so a review of uncommitted changes is an ordinary review of a commit. It's
 * built in an index of its own, so the branch, the index and the working files stay as they were, and no commit hook
 * runs.
 */
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { Refused } from './change.ts';

/** What git printed, run with index as its index. */
function git(index: string, ...args: string[]): string {
  const run = spawnSync('git', args, { env: { ...process.env, GIT_INDEX_FILE: index }, maxBuffer: Infinity });
  if (run.status !== 0) throw new Refused(`git said: ${String(run.stderr ?? run.error).trim()}`);
  return run.stdout.toString('utf8').trim();
}

/**
 * The hash of a commit on top of HEAD that holds every working file git doesn't ignore: tracked edits and deletions,
 * staged or not, and untracked files.
 */
export function snapshot(): string {
  const folder = fs.mkdtempSync(path.join(os.tmpdir(), 'pack-review-index-'));
  try {
    const index = path.join(folder, 'index');
    git(index, 'read-tree', 'HEAD');
    git(index, 'add', '--all');
    const tree = git(index, 'write-tree');
    return git(index, 'commit-tree', tree, '-p', 'HEAD', '-m', 'Uncommitted changes, as pack-review reviews them');
  } finally {
    fs.rmSync(folder, { recursive: true, force: true });
  }
}
