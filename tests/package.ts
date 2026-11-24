/** The npm package as npx gets it: packed, then unpacked into a temp folder. */
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { before } from 'node:test';

import { ROOT } from './scripts.ts';
import { suiteTempDir } from './temp.ts';

/**
 * The path of the packed package's bin, set before the suite that calls this runs, and deleted after it. It packs
 * once per suite, not once per test, since packing compiles dist/ through prepack, which takes seconds.
 */
export function packedBin(): { readonly path: string } {
  const folder = suiteTempDir('context-packs-package-');
  const bin = { path: '' };
  before(() => {
    execFileSync('npm', ['pack', '--silent', '--pack-destination', folder.path], { cwd: ROOT, stdio: 'pipe' });
    const [tarball] = fs.readdirSync(folder.path).filter((name) => name.endsWith('.tgz'));
    execFileSync('tar', ['-xzf', tarball!], { cwd: folder.path });
    bin.path = path.join(folder.path, 'package', 'bin', 'context-packs.js');
  });
  return bin;
}
