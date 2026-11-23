/**
 * The CLI's arguments, read the way Python's argparse read them before: options before the command are the CLI's,
 * options after it are the command's, a usage error prints the usage and exits 2, and -h prints the help.
 */
import { pathlike } from './paths.ts';

export interface Args {
  readonly dir: string;
  readonly command: string | null;
  readonly id: string;
  readonly origin: string;
  readonly path: string;
  readonly ref: string | null;
  readonly when: string | null;
  readonly ids: string[];
  readonly docs: string[];
  readonly pack: string | null;
  readonly runs: number;
  readonly model: string;
  readonly json: boolean;
}

interface Option {
  readonly flag: string;
  readonly key: keyof Args;
  readonly metavar?: string;
  readonly help: string;
}

interface Positional {
  readonly key: keyof Args;
  readonly name: string;
  readonly many?: true;
  readonly help?: string;
}

interface Command {
  readonly help: string;
  readonly options: readonly Option[];
  readonly positionals: readonly Positional[];
}

const COMMANDS: Record<string, Command> = {
  add: {
    help: "install a pack as an import pack in context-packs/<id>/: one from git pinned to its origin's latest commit or "
      + 'to --ref, or a folder on disk read where it is',
    positionals: [
      { key: 'id', name: 'id', help: 'the folder under context-packs/ to put the import pack in, such as core or '
        + 'project/typescript' },
      { key: 'origin', name: 'origin', help: 'a git URL, or the path of a folder on disk, such as docs/agents or '
        + '../agent-config' },
    ],
    options: [
      { flag: '--path', key: 'path', metavar: 'PATH', help: 'the folder in the origin holding the pack, if not its root' },
      { flag: '--ref', key: 'ref', metavar: 'REF', help: 'a tag or commit to pin a pack from git to' },
      { flag: '--when', key: 'when', metavar: 'WHEN', help: "the pack's when, in place of its author's: a row, or "
        + 'always to inline it' },
    ],
  },
  remove: { help: 'uninstall a pack, deleting its import pack', positionals: [{ key: 'id', name: 'id' }], options: [] },
  update: {
    help: "move packs pinned to a commit to the tip of their origin's default branch, leaving those pinned to a tag",
    positionals: [{ key: 'ids', name: 'ids', many: true, help: 'the packs to update; all of them if left out' }],
    options: [{ flag: '--ref', key: 'ref', metavar: 'REF', help: 'a tag or commit to pin the one named pack to instead' }],
  },
  list: { help: 'list the import packs, where each comes from, and its pin', positionals: [], options: [] },
  check: { help: 'exit 1 if a sync would change anything, writing nothing', positionals: [], options: [] },
  docs: {
    help: "print the path of every doc and index the packs' tables point at, one per line, with a blank line between "
      + 'packs, writing nothing',
    positionals: [],
    options: [],
  },
  eval: {
    help: "run each pack's eval prompts: ones that should, or shouldn't, make an agent read a doc, each as a claude -p "
      + 'session with the pack alone',
    positionals: [{ key: 'docs', name: 'docs', many: true, help: 'the docs whose cases to run, as eval names them, '
      + 'such as testing.md or core/testing.md; all of them if left out' }],
    options: [
      { flag: '--pack', key: 'pack', metavar: 'PACK', help: "a pack's folder, relative to the repo, to run only its "
        + 'prompts, whether the repo installs it or not' },
      { flag: '--runs', key: 'runs', metavar: 'RUNS', help: 'how many times to run each prompt, 1 by default' },
      { flag: '--model', key: 'model', metavar: 'MODEL', help: 'the model the sessions use, sonnet by default' },
      { flag: '--json', key: 'json', help: 'print one JSON document of each prompt and its runs once they finish, '
        + 'instead of lines as they go' },
    ],
  },
};

const DESCRIPTION = 'Sync context packs into a repository, or any folder such as the one above the repositories: the '
  + "packs in context-packs/, the repo's own and those its import packs name, as one block in AGENTS.md, with the docs "
  + 'of packs from git and the indexes of nested packs in context-packs/gen/.';

class UsageError extends Error {
  readonly usage: string;
  readonly prog: string;

  constructor(usage: string, prog: string, message: string) {
    super(message);
    this.usage = usage;
    this.prog = prog;
  }
}

function usage(): string {
  return 'usage: context-packs [-h] [--dir DIR] command ...';
}

function commandUsage(name: string, command: Command): string {
  const options = command.options.map((o) => `[${o.flag}${o.metavar ? ` ${o.metavar}` : ''}]`);
  const positionals = command.positionals.map((p) => (p.many ? `[${p.name} ...]` : p.name));
  return ['usage: context-packs', name, '[-h]', ...options, ...positionals].join(' ');
}

function help(): string {
  return [
    usage(), '', DESCRIPTION, '', 'options:', '  -h, --help  show this help message and exit',
    '  --dir DIR   the folder to sync, if not the current one', '', 'commands:',
    '  leave out the command to resync every pack at its pinned ref', '',
    ...Object.entries(COMMANDS).map(([name, command]) => `  ${name}  ${command.help}`),
  ].join('\n') + '\n';
}

function commandHelp(name: string, command: Command): string {
  return [
    commandUsage(name, command), '', ...(command.positionals.length ? ['positional arguments:'] : []),
    ...command.positionals.map((p) => `  ${p.name}  ${p.help ?? ''}`.trimEnd()), '', 'options:',
    '  -h, --help  show this help message and exit',
    ...command.options.map((o) => `  ${o.flag}${o.metavar ? ` ${o.metavar}` : ''}  ${o.help}`),
  ].join('\n') + '\n';
}

/** The arguments argv holds, or an exit: 0 after printing help, 2 after a usage error. */
export function parse(argv: readonly string[], cwd: string): Args {
  try {
    return read(argv, cwd);
  } catch (error) {
    if (!(error instanceof UsageError)) throw error;
    process.stderr.write(`${error.usage}\n${error.prog}: error: ${error.message}\n`);
    process.exit(2);
  }
}

function read(argv: readonly string[], cwd: string): Args {
  const values: Record<string, unknown> = {
    dir: cwd, command: null, id: '', origin: '', path: '', ref: null, when: null, ids: [], docs: [], pack: null,
    runs: '1', model: 'sonnet', json: false,
  };
  let i = 0;
  // The CLI's own options, before the command.
  for (; i < argv.length && argv[i]!.startsWith('-'); i++) {
    const [flag, inline] = split(argv[i]!);
    if (flag === '-h' || flag === '--help') {
      process.stdout.write(help());
      process.exit(0);
    }
    if (flag !== '--dir') throw new UsageError(usage(), 'context-packs', `unrecognized arguments: ${argv.slice(i).join(' ')}`);
    const value = inline ?? argv[++i];
    if (value === undefined) throw new UsageError(usage(), 'context-packs', 'argument --dir: expected one argument');
    values.dir = value;
  }
  const name = argv[i++];
  if (name !== undefined) {
    const command = COMMANDS[name];
    if (!command) {
      const choices = Object.keys(COMMANDS).map((c) => `'${c}'`).join(', ');
      throw new UsageError(usage(), 'context-packs', `argument command: invalid choice: '${name}' (choose from ${choices})`);
    }
    values.command = name;
    readCommand(name, command, argv.slice(i), values);
  }
  const runs = Number(values.runs);
  if (!/^[+-]?\d+$/.test(String(values.runs).trim())) {
    const command = COMMANDS.eval!;
    throw new UsageError(commandUsage('eval', command), 'context-packs eval',
                         `argument --runs: invalid int value: '${values.runs}'`);
  }
  return { ...values, dir: pathlike(String(values.dir)), runs } as unknown as Args;
}

function split(arg: string): [string, string | undefined] {
  const equals = arg.indexOf('=');
  return arg.startsWith('--') && equals !== -1 ? [arg.slice(0, equals), arg.slice(equals + 1)] : [arg, undefined];
}

function readCommand(name: string, command: Command, argv: readonly string[], values: Record<string, unknown>): void {
  const prog = `context-packs ${name}`;
  const positionals: string[] = [];
  const unknown: string[] = [];
  let options = true;
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i]!;
    if (options && arg === '--') {
      options = false;
      continue;
    }
    if (!options || !arg.startsWith('-') || arg === '-') {
      positionals.push(arg);
      continue;
    }
    const [flag, inline] = split(arg);
    if (flag === '-h' || flag === '--help') {
      process.stdout.write(commandHelp(name, command));
      process.exit(0);
    }
    const option = command.options.find((o) => o.flag === flag);
    if (!option) {
      unknown.push(arg);
      continue;
    }
    if (!option.metavar) {
      values[option.key] = true;
      continue;
    }
    const value = inline ?? argv[++i];
    if (value === undefined || (inline === undefined && value.startsWith('-') && value !== '-')) {
      throw new UsageError(commandUsage(name, command), prog, `argument ${flag}: expected one argument`);
    }
    values[option.key] = value;
  }
  const single = command.positionals.filter((p) => !p.many);
  const missing = single.slice(positionals.length).map((p) => p.name);
  if (missing.length) {
    throw new UsageError(commandUsage(name, command), prog, `the following arguments are required: ${missing.join(', ')}`);
  }
  single.forEach((p, n) => (values[p.key] = positionals[n]));
  const many = command.positionals.find((p) => p.many);
  const rest = positionals.slice(single.length);
  if (many) values[many.key] = rest;
  else unknown.unshift(...rest);
  if (unknown.length) throw new UsageError(usage(), 'context-packs', `unrecognized arguments: ${unknown.join(' ')}`);
}
