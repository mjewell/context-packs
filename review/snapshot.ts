/**
 * A commit made from the working files, so a review of uncommitted changes is an ordinary review of a commit. It's
 * built in an index of its own, so the branch, the index and the working files stay as they were, and no commit hook
 * runs.
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { gitWithEnv } from './change.ts';

/** What git printed, trimmed, run with index as its index. */
function gitWithIndex(index: string, ...args: string[]): string {
  return gitWithEnv({ GIT_INDEX_FILE: index }, ...args).trim();
}

/**
 * The hash of a commit on top of HEAD that holds every working file git doesn't ignore: tracked edits and deletions,
 * staged or not, and untracked files.
 */
export function snapshot(): string {
  const folder = fs.mkdtempSync(path.join(os.tmpdir(), 'pack-review-index-'));
  try {
    const index = path.join(folder, 'index');
    gitWithIndex(index, 'read-tree', 'HEAD');
    gitWithIndex(index, 'add', '--all');
    const tree = gitWithIndex(index, 'write-tree');
    return gitWithIndex(
      index,
      'commit-tree',
      tree,
      '-p',
      'HEAD',
      '-m',
      'Uncommitted changes, as pack-review reviews them',
    );
  } finally {
    fs.rmSync(folder, { recursive: true, force: true });
  }
}
