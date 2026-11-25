/**
 * The repo and runs the wizard's tests share: a change against two packs' tables, and helpers that run its steps as
 * an agent would.
 */
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';

import { GitCase, withoutGit } from './git_case.ts';
import { command, type Result, run } from './scripts.ts';
import { tempDir } from './temp.ts';

// The block as a sync writes it, so the CLI's check that it wasn't edited passes.
const BODY = `## Context

| When | Read |
|---|---|
| Writing tests | \`docs/testing.md\` |
| Committing | \`docs/git.md\` |

## style context

| When | Read |
|---|---|
| Writing prose | \`docs/prose.md\` |
`;
const AGENTS =
  `# Repo\n\n<!-- context-packs:start -->\n${BODY}` +
  `<!-- context-packs:end sha256:${createHash('sha256').update(BODY).digest('hex').slice(0, 12)} -->\n`;
const DOCS = {
  'docs/testing.md': '# Testing\n\nTest behavior.\n',
  'docs/git.md': '# Git\n\nSmall commits.\n',
  'docs/prose.md': '# Prose\n\nShort sentences.\n',
};

/**
 * A repo whose instruction file has two packs' tables, so the review has two pack units after the instruction file's,
 * and a change on top of its base that edits one file and adds another. The wizard runs in it the way an agent runs
 * it, as a command.
 */
export class WizardCase extends GitCase {
  head!: string;
  env!: NodeJS.ProcessEnv;
  runDir = '';

  protected override async setUp(): Promise<void> {
    await super.setUp();
    this.commit('Add the packs and the app', { 'AGENTS.md': AGENTS, ...DOCS, 'src/app.py': 'x = 1\n' });
    this.base = this.git('rev-parse', 'HEAD');
    this.head = this.commit('Change the app', { 'src/app.py': 'x = 2\n', 'tests/test_app.py': 'assert True\n' });
    this.env = withoutGit({ TMPDIR: tempDir(this.t, 'context-packs-runs-') });
  }

  wizard(...args: string[]): Promise<Result> {
    return run([...command('review/wizard'), ...args], { cwd: this.repo, env: this.env });
  }

  /** What init printed, once it succeeded. The run folder it made is in every command it prints. */
  async init(): Promise<string> {
    const result = await this.wizard('init', '--base', this.base, '--head', 'HEAD', '--command', 'review');
    assert.equal(result.status, 0, result.stderr);
    this.runDir = /review --run (\S+) /.exec(result.stdout)![1]!;
    return result.stdout;
  }

  /** A command as the wizard prints it for this run. */
  command(...args: string[]): string {
    return ['review', '--run', this.runDir, ...args].join(' ');
  }

  /** Where an agent writes one of this run's answers, such as unit-1.json. */
  answerPath(name: string): string {
    return path.join(this.env.TMPDIR!, 'pack-review-answers', path.basename(this.runDir), name);
  }
}

/** A run init started. */
export class StartedCase extends WizardCase {
  protected override async setUp(): Promise<void> {
    await super.setUp();
    await this.init();
  }

  /** A step of this run: what it printed, and what it printed as an error, with its exit code. */
  step(...args: string[]): Promise<Result> {
    return this.wizard('--run', this.runDir, ...args);
  }

  /** The merging agent's groups, written where its brief says, then submitted. */
  submitGroups(groups: readonly unknown[]): Promise<Result> {
    fs.writeFileSync(this.answerPath('groups.json'), JSON.stringify({ groups }));
    return this.step('submit-groups');
  }
}

export function deviation(headline = 'Tests reach into a private helper', file = 'tests/test_app.py', line = 1) {
  return {
    kind: 'deviation',
    headline,
    rules: [{ file: 'docs/testing.md', quote: 'Test behavior.', routed: true }] as unknown[],
    spots: [{ path: file, line, follows: false }] as { path: string; line: unknown; follows: boolean }[],
    deliberate: [] as string[],
    exemplars: [] as unknown[],
    take: 'Test through the public interface.',
  };
}

/** A finder at the end of its brief: it read its docs, writes its answer where the brief says, and submits it. */
export class SubmitCase extends StartedCase {
  submit(finder: number, findings: string | readonly unknown[]): Promise<Result> {
    const text = typeof findings === 'string' ? findings : JSON.stringify({ findings });
    fs.writeFileSync(this.answerPath(`unit-${finder}.json`), text);
    return this.step('submit', String(finder));
  }

  async readDocs(unit: number, count: number): Promise<void> {
    for (let n = 1; n <= count; n++) {
      const result = await this.step('doc', String(unit), String(n));
      assert.equal(result.status, 0, result.stderr);
    }
  }

  async submitUnit(unit: number, docs: number, findings: readonly unknown[]): Promise<void> {
    await this.readDocs(unit, docs);
    const result = await this.submit(unit, findings);
    assert.equal(result.status, 0, result.stderr);
  }
}

/** Every finder in: units 0 and 1 with one deviation each, unit 2 with none, and the uncovered finder with one. */
export class MergeCase extends SubmitCase {
  async allIn(): Promise<void> {
    await this.submitUnit(0, 1, [deviation('A')]);
    await this.submitUnit(1, 2, [deviation('B')]);
    await this.submitUnit(2, 1, []);
    assert.equal((await this.submit(3, [{ ...deviation('D'), kind: 'uncovered choice', rules: [] }])).status, 0);
    assert.equal((await this.step('next')).status, 0);
  }
}

/** A review that's done, with a finding of each kind: unit 0's deviation, unit 1's as a conflict, and the uncovered choice. */
export class DoneCase extends MergeCase {
  protected override async setUp(): Promise<void> {
    await super.setUp();
    await this.allIn();
    const result = await this.submitGroups([
      { ids: ['0:0'], kind: 'deviation', headline: 'Tests reach into a helper', take: 'T' },
      { ids: ['1:0'], kind: 'conflict', headline: 'Two rules on one import', take: 'C' },
      { ids: ['3:0'], kind: 'uncovered choice', headline: 'Where config lives', take: 'U' },
    ]);
    assert.equal(result.status, 0, result.stderr);
  }

  /** The findings the merge built, as the run keeps them. */
  findings(): { kind: string; headline: string }[] {
    return JSON.parse(fs.readFileSync(path.join(this.runDir, 'findings.json'), 'utf8')).findings;
  }
}
