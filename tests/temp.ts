import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { after, before, type TestContext } from 'node:test';

/**
 * A new folder in the system's temp folder. Its path has its links resolved, as the scripts see it, since macOS's
 * temp folder is under a link.
 */
function made(prefix: string): string {
  return fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), prefix)));
}

function removed(folder: string): void {
  fs.rmSync(folder, { recursive: true, force: true });
}

/** A new temp folder, deleted when the test ends. */
export function tempDir(t: TestContext, prefix: string): string {
  const folder = made(prefix);
  t.after(() => removed(folder));
  return folder;
}

/**
 * A temp folder for a whole suite, made before its first test and deleted after its last. Call it in the describe, so
 * its path is set by the time the suite's own before hooks run.
 */
export function suiteTempDir(prefix: string): { readonly path: string } {
  const folder = { path: '' };
  before(() => {
    folder.path = made(prefix);
  });
  after(() => removed(folder.path));
  return folder;
}
