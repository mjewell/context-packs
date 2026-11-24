/** The pairing job's case, which the start tests share for its step outputs. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

import { BASE, HEAD, ReviewCase } from './review_case.ts';

/** A finding at one spot, as the review's report holds it. */
export function finding(headline: string, { file = 'src/sim.ts', line = 42, kind = 'deviation' } = {}) {
  return {
    kind,
    headline,
    rules: [] as unknown[],
    spots: [{ path: file, line, follows: false }],
    deliberate: [] as string[],
    exemplars: [] as unknown[],
    take: 'Move it to content.',
  };
}

export const F1 = finding('A game number in sim code');
export const F3 = finding('A second RNG', { file: 'src/rng.ts', line: 17 });

/**
 * The pairing job, between review and post: the review job's report, and pack-review's threads as threads.ts prints
 * them.
 */
export class PairingCase extends ReviewCase {
  output = '';

  protected override async setUp(): Promise<void> {
    await super.setUp();
    this.output = path.join(this.root, 'github-output.txt');
    fs.writeFileSync(this.output, '');
    this.env.GITHUB_OUTPUT = this.output;
  }

  given(findings: readonly unknown[], threads: readonly unknown[], head = HEAD): void {
    fs.writeFileSync(
      path.join(this.root, 'report.json'),
      JSON.stringify({ base: BASE, base_ref: 'main', head, findings }),
    );
    fs.writeFileSync(path.join(this.root, 'threads.json'), JSON.stringify(threads));
  }

  /** The step outputs written to GITHUB_OUTPUT, each value whole. */
  outputs(): Record<string, string> {
    const text = fs.readFileSync(this.output, 'utf8');
    const found: Record<string, string> = {};
    for (const [, name, , value] of text.matchAll(/^(\w[\w-]*)<<(\S+)\n([\s\S]*?)\n\2$/gm)) found[name!] = value!;
    return found;
  }

  async prompt(): Promise<Record<string, string>> {
    const run = await this.script('pairing', 'pair-prompt', '--report', 'report.json', '--threads', 'threads.json');
    assert.equal(run.status, 0, run.stderr);
    return this.outputs();
  }

  check(pairs?: string | readonly unknown[]) {
    const args = pairs === undefined ? [] : ['--pairs', 'pairs.json'];
    if (pairs !== undefined) {
      fs.writeFileSync(
        path.join(this.root, 'pairs.json'),
        typeof pairs === 'string' ? pairs : JSON.stringify({ pairs }),
      );
    }
    return this.script(
      'pairing',
      'pair-check',
      '--report',
      'report.json',
      '--threads',
      'threads.json',
      ...args,
      '--out',
      'paired.json',
    );
  }

  matched() {
    return JSON.parse(fs.readFileSync(path.join(this.root, 'paired.json'), 'utf8'));
  }
}
