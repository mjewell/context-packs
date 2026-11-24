/** A repo to sync and a pack's origin to sync from, and the text a sync writes, for the sync CLI's tests. */
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

import { Case } from './case.ts';
import { command, environment, type Result, run } from './scripts.ts';
import { tempDir } from './temp.ts';

export const START = '<!-- context-packs:start -->\n';
// The end marker with its hash masked, as SyncCase.agents() reads it.
export const END = '<!-- context-packs:end sha256:x -->\n';
export const EMPTY = `${START}<!-- context-packs:end sha256:e3b0c44298fc -->\n`;
// What the header says in a repo about where paths start, since the tables' paths aren't absolute.
export const CLAUSE =
  'The paths in these tables start from the repo root. ' +
  "Look for a path a doc names in the doc's folder first, then from the repo root. ";
// What it says instead in a folder in no repo, where the tables' paths are absolute.
export const OUTSIDE_CLAUSE =
  "Look for a path a doc names in the doc's folder first, then from the folder the session started in. ";
export const HEADER =
  '## Context Packs\n\n' +
  'Context packs bring shared rules and docs in from elsewhere. Each pack has its pack rules and a table of its ' +
  'pack docs here, and a doc may hold a table of its own. Before starting work that a row in any of these ' +
  `tables matches, read its doc. ${CLAUSE}The packs here, and everything under \`context-packs/gen/\`, are ` +
  'generated from `context-packs/`: change them there, never here.\n';

/** The context-packs block holding the header and body, with its hash masked. */
export function block(body = ''): string {
  return START + HEADER + (body ? `\n${body}` : '') + END;
}

/** A pack inlined into the block or an index, between the markers naming it. */
export function packed(id: string, body: string): string {
  return `<!-- context-packs:pack ${id} -->\n${body}<!-- context-packs:pack-end ${id} -->\n`;
}

export function masked(text: string): string {
  return text.replace(/sha256:[0-9a-f]{12}/g, 'sha256:x');
}

/** A doc with its when line and any other front matter fields, then text. */
export function doc(when: string, text = '', fields: Readonly<Record<string, string>> = {}): string {
  const front = Object.entries(fields)
    .map(([key, value]) => `${key}: ${value}\n`)
    .join('');
  return `---\nwhen: ${when}\n${front}---\n${text}`;
}

export function git(cwd: string, ...args: string[]): string {
  return execFileSync('git', ['-c', 'user.name=Test', '-c', 'user.email=test@example.com', ...args], {
    cwd,
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
  }).trim();
}

export function read(file: string): string {
  return fs.readFileSync(file, 'utf8');
}

export function exists(file: string): boolean {
  return fs.existsSync(file);
}

/** The names in a folder, sorted. */
export function names(folder: string): string[] {
  return fs.readdirSync(folder).sort();
}

/** A repo to sync, and a pack's origin with a checkout of it, so tests control the pack's content. */
export class SyncCase extends Case {
  root!: string;
  origin!: string;
  source!: string;
  repo!: string;
  packs!: string;
  gen!: string;
  agentsMd!: string;
  env!: NodeJS.ProcessEnv;

  protected override async setUp(): Promise<void> {
    this.root = tempDir(this.t, 'context-packs-test-');
    [this.origin, this.source] = this.remote('house-rules');
    this.repo = path.join(this.root, 'repo');
    fs.mkdirSync(path.join(this.repo, '.git'), { recursive: true });
    this.packs = path.join(this.repo, 'context-packs');
    this.gen = path.join(this.packs, 'gen');
    this.agentsMd = path.join(this.repo, 'AGENTS.md');
    this.env = environment({ XDG_CACHE_HOME: path.join(this.root, 'cache') });
  }

  /** A bare origin, by its git URL, and a checkout of it. */
  remote(name: string): [string, string] {
    const origin = path.join(this.root, `${name}.git`);
    git(this.root, 'init', '--quiet', '--bare', '--initial-branch=main', origin);
    git(this.root, 'clone', '--quiet', origin, path.join(this.root, name));
    return [pathToFileURL(origin).href, path.join(this.root, name)];
  }

  /** Commit files into a pack's folder, null deleting one, and push them to its origin. Returns the commit. */
  publish(files: Readonly<Record<string, string | null>>, checkout = this.source, folder = 'context'): string {
    for (const [file, text] of Object.entries(files)) {
      const target = path.join(checkout, folder, file);
      if (text === null) {
        git(checkout, 'rm', '--quiet', '-r', target);
        continue;
      }
      fs.mkdirSync(path.dirname(target), { recursive: true });
      fs.writeFileSync(target, text);
    }
    git(checkout, 'add', '--all', folder);
    git(checkout, 'commit', '--quiet', '-m', 'Change the pack');
    git(checkout, 'push', '--quiet', 'origin', 'HEAD:main');
    return git(checkout, 'rev-parse', 'HEAD');
  }

  share(instructions: string): string {
    return this.publish({ 'pack.md': instructions });
  }

  tag(name: string, checkout = this.source): void {
    git(checkout, 'tag', name);
    git(checkout, 'push', '--quiet', 'origin', name);
  }

  /** Write a file in the repo. */
  write(file: string, text: string): string {
    const target = path.join(this.repo, file);
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.writeFileSync(target, text);
    return target;
  }

  /** AGENTS.md with its block's hash masked. */
  agents(): string {
    return masked(read(this.agentsMd));
  }

  /** AGENTS.md as a sync writes it from the pack rules 'Prefer small PRs.', with no docs. */
  rules(): string {
    return block(packed('house-rules', 'Prefer small PRs.\n'));
  }

  importMd(id = 'house-rules'): string {
    return path.join(this.packs, id, 'pack.md');
  }

  /** An import pack's front matter, as add writes it. */
  front(ref: string, { when, origin, folder = 'context' }: { when?: string; origin?: string; folder?: string } = {}) {
    return (
      '---\n' +
      (when ? `when: ${when}\n` : '') +
      `from: ${origin ?? this.origin}\n` +
      (folder ? `path: ${folder}\n` : '') +
      `ref: ${ref}\n---\n`
    );
  }

  /** The ref the pack's import pack pins it to. */
  pin(id = 'house-rules'): string {
    const line = read(this.importMd(id))
      .split('\n')
      .find((l) => l.startsWith('ref: '));
    return line!.slice('ref: '.length);
  }

  sync(...args: string[]): Promise<Result> {
    return this.syncIn(this.repo, ...args);
  }

  /** A sync run from cwd rather than the repo. */
  syncIn(cwd: string, ...args: string[]): Promise<Result> {
    return run([...command('src/cli'), ...args], { cwd, env: this.env, timeout: 30_000 });
  }

  add(...args: string[]): Promise<Result> {
    return this.addAs('house-rules', ...args);
  }

  /** add of the house-rules origin under another id. */
  addAs(id: string, ...args: string[]): Promise<Result> {
    return this.sync('add', id, this.origin, '--path', 'context', ...args);
  }
}
