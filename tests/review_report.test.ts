import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { describe, test } from 'node:test';

import { exits, includes } from './expect.ts';
import { HEAD, ReviewCase, spot } from './review_case.ts';

const BASE = 'b'.repeat(40);
const NUMBERS = { file: 'AGENTS.md', quote: 'Game numbers live in content.', routed: true };

/** One finder's finding. */
function finding(id: string, { rules = [] as unknown[], spots = [] as unknown[], kind = 'deviation' } = {}) {
  return {
    kind,
    headline: `Finder headline ${id}`,
    rules,
    spots,
    deliberate: [],
    exemplars: [],
    take: `Finder take ${id}.`,
  };
}

/**
 * The review job after its agent: the findings the wizard built, and the head lines each diff shows. A review that
 * ran the wizard already built its findings, so the report starts from them: it adds the base branch and the line
 * each finding's thread opens on, and refuses findings for another head.
 */
class FindingsCase extends ReviewCase {
  fromFindings(findings: readonly unknown[], head = HEAD, shown: Record<string, number[]> = {}) {
    fs.writeFileSync(path.join(this.root, 'findings.json'), JSON.stringify({ base: BASE, head, findings }));
    fs.writeFileSync(path.join(this.root, 'shown.json'), JSON.stringify(shown));
    return this.script(
      'report',
      '--base',
      BASE,
      '--base-ref',
      'main',
      '--head',
      HEAD,
      '--findings',
      'findings.json',
      '--shown',
      'shown.json',
      '--out',
      'report.json',
    );
  }

  report() {
    return JSON.parse(fs.readFileSync(path.join(this.root, 'report.json'), 'utf8'));
  }
}

describe('report', () => {
  test('reports the wizards findings with their anchors', async (t) => {
    const c = await FindingsCase.make(t);
    const found = finding('0:0', { rules: [NUMBERS], spots: [spot('src/sim.ts', 42)] });

    const run = await c.fromFindings([found], HEAD, { 'src/sim.ts': [41, 42] });

    exits(run, 0);
    assert.deepEqual(c.report(), {
      base: BASE,
      base_ref: 'main',
      head: HEAD,
      findings: [found],
      anchors: [{ path: 'src/sim.ts', line: 42 }],
    });
  });

  test('cleans the findings text like the merges', async (t) => {
    const c = await FindingsCase.make(t);
    const found = { ...finding('0:0'), headline: 'A zero​width space' };

    assert.equal((await c.fromFindings([found])).status, 0);

    const [reported] = c.report().findings;
    assert.equal(reported.headline, 'A zerowidth space');
  });

  test('refuses findings for another head', async (t) => {
    const c = await FindingsCase.make(t);
    const run = await c.fromFindings([], 'x'.repeat(40));

    exits(run, 1);
    includes(run.stderr, `pack-review: the review's findings are for ${'x'.repeat(40)}, not the head, ${HEAD}.`);
    assert.ok(!fs.existsSync(path.join(c.root, 'report.json')));
  });
});
