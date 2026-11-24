/** The npm package as npx gets it: packed, then unpacked into a temp folder. */
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { after, before } from 'node:test';

import { ROOT } from './scripts.ts';

/**
 * The path of the packed package's bin, set before the suite that calls this runs, and deleted after it. Packing
 * compiles dist/ through prepack, so the bin runs the CLI as published.
 */
export function packedBin(): { readonly path: string } {
  let folder = '';
  const bin = { path: '' };
  before(() => {
    folder = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'context-packs-package-')));
    execFileSync('npm', ['pack', '--silent', '--pack-destination', folder], { cwd: ROOT, stdio: 'pipe' });
    const [tarball] = fs.readdirSync(folder).filter((name) => name.endsWith('.tgz'));
    execFileSync('tar', ['-xzf', tarball!], { cwd: folder });
    bin.path = path.join(folder, 'package', 'bin', 'context-packs.js');
  });
  after(() => fs.rmSync(folder, { recursive: true, force: true }));
  return bin;
}
