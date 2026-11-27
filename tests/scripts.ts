/**
 * How the tests run the repo's scripts: each as its own process, with node. The tests check what a script prints and
 * does, never how it's written, so moving code between modules never breaks one.
 */
import { spawn } from 'node:child_process';
import path from 'node:path';

import { quote } from './shlex.ts';

export const ROOT = path.resolve(import.meta.dirname, '..');

/** What a script did: its exit code, null when a signal ended it, and what it printed. */
export interface Result {
  readonly status: number | null;
  readonly stdout: string;
  readonly stderr: string;
}

export interface RunOptions {
  readonly cwd: string;
  readonly env?: NodeJS.ProcessEnv;
  readonly input?: string;
  // Milliseconds before the process is killed, so a script that hangs fails its test instead of the whole run.
  readonly timeout?: number;
}

/** The command that runs script, such as 'src/cli', as a list of arguments. */
export function command(script: string): string[] {
  return ['node', path.join(ROOT, `${script}.ts`)];
}

/** The command that runs script, as one line for a shell. */
export function shell(script: string): string {
  return command(script).map(quote).join(' ');
}

/**
 * This process's environment with extra on top, for a script to run in. node --test tells the processes it starts
 * that they report to it, through NODE_TEST_CONTEXT, so that's left out: the scripts under test aren't test files.
 */
export function environment(extra: NodeJS.ProcessEnv = {}): NodeJS.ProcessEnv {
  const { NODE_TEST_CONTEXT: _, ...rest } = process.env;
  return { ...rest, ...extra };
}

/**
 * Runs argv and resolves with what it did, whatever its exit code. Async, since a test's fake GitHub answers from
 * this process while the script runs.
 */
export function run(argv: readonly string[], options: RunOptions): Promise<Result> {
  const [file, ...args] = argv;
  return new Promise((resolve, reject) => {
    const child = spawn(file!, args, {
      cwd: options.cwd,
      env: options.env ?? environment(),
      timeout: options.timeout ?? 60_000,
    });
    let stdout = '';
    let stderr = '';
    child.stdout.setEncoding('utf8').on('data', (chunk: string) => {
      stdout += chunk;
    });
    child.stderr.setEncoding('utf8').on('data', (chunk: string) => {
      stderr += chunk;
    });
    child.on('error', reject);
    child.on('close', (status) => resolve({ status, stdout, stderr }));
    child.stdin.end(options.input ?? '');
  });
}
