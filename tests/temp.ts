import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import type { TestContext } from 'node:test';

/**
 * A new folder in the system's temp folder, deleted when the test ends. Its path has its links resolved, as the
 * scripts see it, since macOS's temp folder is under a link.
 */
export function tempDir(t: TestContext, prefix: string): string {
  const folder = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), prefix)));
  t.after(() => fs.rmSync(folder, { recursive: true, force: true }));
  return folder;
}
