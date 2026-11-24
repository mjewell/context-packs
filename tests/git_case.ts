/** A git repo in a temporary folder, with a base commit and commits on top of it. */
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { Case } from './case.ts';
import { tempDir } from './temp.ts';

export class GitCase extends Case {
  repo!: string;
  base!: string;

  protected override async setUp(): Promise<void> {
    this.repo = tempDir(this.t, 'context-packs-git-');
    this.git('init', '-q', '-b', 'main');
    this.git('config', 'user.name', 'Test');
    this.git('config', 'user.email', 'test@example.com');
    this.git('commit', '-q', '--allow-empty', '-m', 'Start');
    this.base = this.git('rev-parse', 'HEAD');
  }

  git(...args: string[]): string {
    return execFileSync('git', args, { cwd: this.repo, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }).trim();
  }

  /** A commit on top of the last that writes each of files, by path, and deletes each of removed. Its hash. */
  commit(message: string, files: Readonly<Record<string, string>> = {}, removed: readonly string[] = []): string {
    for (const [file, text] of Object.entries(files)) {
      const target = path.join(this.repo, file);
      fs.mkdirSync(path.dirname(target), { recursive: true });
      fs.writeFileSync(target, text);
      this.git('add', '--', file);
    }
    for (const file of removed) this.git('rm', '-q', '--', file);
    this.git('commit', '-q', '-m', message);
    return this.git('rev-parse', 'HEAD');
  }
}

/** This process's environment without git's own variables, which would point a script's git at another repo. */
export function withoutGit(extra: NodeJS.ProcessEnv): NodeJS.ProcessEnv {
  const env: NodeJS.ProcessEnv = {};
  for (const [key, value] of Object.entries(process.env)) {
    if (!key.startsWith('GIT_') && key !== 'NODE_TEST_CONTEXT') env[key] = value;
  }
  return { ...env, ...extra };
}
