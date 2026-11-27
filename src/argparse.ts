/**
 * Command-line arguments read the way Python's argparse read them, for the CLI, which was Python: options before a command are the program's, options after it are the command's, `--` ends the options, an
 * option is never matched by a shortened name, a usage error prints the usage and exits 2, and -h prints the help.
 */

export interface Option {
  readonly flag: string;
  readonly dest: string;
  /** The value's name in the usage. An option without one is a flag, true when given. */
  readonly metavar?: string;
  readonly required?: true;
  readonly default?: string | boolean | null;
  readonly help: string;
}

export interface Positional {
  readonly dest: string;
  /** '?' for one that may be left out, '*' for any number. */
  readonly nargs?: '?' | '*';
  readonly default?: string;
  readonly help?: string;
}

export interface Command {
  readonly help: string;
  readonly options?: readonly Option[];
  readonly positionals?: readonly Positional[];
}

export interface Parser extends Command {
  readonly prog: string;
  readonly description?: string;
  /** The commands, by name. Without them, the parser takes its options and positionals alone. */
  readonly commands?: Readonly<Record<string, Command>>;
  readonly commandRequired?: true;
  /** The value that holds which command ran, 'command' unless a command has an option of that name. */
  readonly commandDest?: string;
}

export type Values = Record<string, unknown>;

class UsageError extends Error {
  readonly usage: string;
  readonly prog: string;

  constructor(usage: string, prog: string, message: string) {
    super(message);
    this.usage = usage;
    this.prog = prog;
  }
}

function shown(option: Option): string {
  return option.metavar ? `${option.flag} ${option.metavar}` : option.flag;
}

function usage(prog: string, command: Command, commands = false): string {
  const options = (command.options ?? []).map((o) => (o.required ? shown(o) : `[${shown(o)}]`));
  const positionals = (command.positionals ?? []).map((p) =>
    p.nargs === '*' ? `[${p.dest} ...]` : p.nargs === '?' ? `[${p.dest}]` : p.dest,
  );
  return ['usage:', prog, '[-h]', ...options, ...positionals, ...(commands ? ['command ...'] : [])].join(' ');
}

function help(
  prog: string,
  command: Command,
  description?: string,
  commands?: Readonly<Record<string, Command>>,
): string {
  const lines = [usage(prog, command, !!commands), ''];
  if (description) lines.push(description, '');
  const positionals = command.positionals ?? [];
  if (positionals.length)
    lines.push('positional arguments:', ...positionals.map((p) => `  ${p.dest}  ${p.help ?? ''}`.trimEnd()), '');
  lines.push('options:', '  -h, --help  show this help message and exit');
  lines.push(...(command.options ?? []).map((o) => `  ${shown(o)}  ${o.help}`));
  if (commands) {
    lines.push('', 'commands:', ...Object.entries(commands).map(([name, c]) => `  ${name}  ${c.help}`));
  }
  return `${lines.join('\n')}\n`;
}

/** The values argv holds, or an exit: 0 after printing help, 2 after a usage error. */
export function parse(parser: Parser, argv: readonly string[]): Values {
  try {
    return read(parser, argv);
  } catch (error) {
    if (!(error instanceof UsageError)) throw error;
    return usageError(error.usage, error.prog, error.message);
  }
}

/** Print a usage error and exit 2, as argparse's parser.error does. */
export function usageError(usageLine: string, prog: string, message: string): never {
  process.stderr.write(`${usageLine}\n${prog}: error: ${message}\n`);
  process.exit(2);
}

/** The usage line of the parser, as an error after parsing prints it. */
export function usageOf(parser: Parser): string {
  return usage(parser.prog, parser, !!parser.commands);
}

function defaults(command: Command, values: Record<string, unknown>): void {
  for (const option of command.options ?? []) values[option.dest] = option.default ?? (option.metavar ? null : false);
  for (const positional of command.positionals ?? []) {
    values[positional.dest] = positional.nargs === '*' ? [] : (positional.default ?? null);
  }
}

function read(parser: Parser, argv: readonly string[]): Values {
  const values: Record<string, unknown> = { [parser.commandDest ?? 'command']: null };
  defaults(parser, values);
  const commands = parser.commands;
  const topUsage = usage(parser.prog, parser, !!commands);
  if (!commands) {
    readArgs(parser.prog, topUsage, parser, argv, values, () => help(parser.prog, parser, parser.description));
    return values as Values;
  }
  // The program's own options come before the command.
  let i = 0;
  const own: string[] = [];
  for (; i < argv.length && argv[i]!.startsWith('-') && argv[i] !== '--'; i++) {
    own.push(argv[i]!);
    const option = (parser.options ?? []).find((o) => o.flag === split(argv[i]!)[0]);
    if (option?.metavar && split(argv[i]!)[1] === undefined && i + 1 < argv.length) own.push(argv[++i]!);
  }
  readArgs(parser.prog, topUsage, parser, own, values, () => help(parser.prog, parser, parser.description, commands));
  const name = argv[i++];
  if (name === undefined) {
    if (parser.commandRequired)
      throw new UsageError(topUsage, parser.prog, 'the following arguments are required: command');
    return values as Values;
  }
  const command = commands[name];
  if (!command) {
    const choices = Object.keys(commands)
      .map((c) => `'${c}'`)
      .join(', ');
    throw new UsageError(topUsage, parser.prog, `argument command: invalid choice: '${name}' (choose from ${choices})`);
  }
  values[parser.commandDest ?? 'command'] = name;
  defaults(command, values);
  const prog = `${parser.prog} ${name}`;
  readArgs(
    prog,
    usage(prog, command),
    command,
    argv.slice(i),
    values,
    () => help(prog, command),
    topUsage,
    parser.prog,
  );
  return values as Values;
}

function split(arg: string): [string, string | undefined] {
  const equals = arg.indexOf('=');
  return arg.startsWith('--') && equals !== -1 ? [arg.slice(0, equals), arg.slice(equals + 1)] : [arg, undefined];
}

/**
 * Read one parser's or command's options and positionals from argv into values. Arguments it doesn't take are an
 * error at the top level, as argparse reports them after every command has parsed what it knows.
 */
function readArgs(
  prog: string,
  usageLine: string,
  command: Command,
  argv: readonly string[],
  values: Record<string, unknown>,
  helpText: () => string,
  topUsage = usageLine,
  topProg = prog,
): void {
  const options = command.options ?? [];
  const positionals: string[] = [];
  const unknown: string[] = [];
  const given = new Set<string>();
  let ended = false;
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i]!;
    if (!ended && arg === '--') {
      ended = true;
      continue;
    }
    // A negative number is a value, as argparse reads one when no option looks like a number.
    if (ended || !arg.startsWith('-') || arg === '-' || /^-\d+$|^-\d*\.\d+$/.test(arg)) {
      positionals.push(arg);
      continue;
    }
    const [flag, inline] = split(arg);
    if (flag === '-h' || flag === '--help') {
      process.stdout.write(helpText());
      process.exit(0);
    }
    const option = options.find((o) => o.flag === flag);
    if (!option) {
      unknown.push(arg);
      continue;
    }
    given.add(option.dest);
    if (!option.metavar) {
      values[option.dest] = true;
      continue;
    }
    const value = inline ?? argv[++i];
    if (value === undefined || (inline === undefined && value.startsWith('-') && value !== '-')) {
      throw new UsageError(usageLine, prog, `argument ${flag}: expected one argument`);
    }
    values[option.dest] = value;
  }
  const specs = command.positionals ?? [];
  const single = specs.filter((p) => !p.nargs);
  const missing = [
    ...options.filter((o) => o.required && !given.has(o.dest)).map((o) => o.flag),
    ...single.slice(positionals.length).map((p) => p.dest),
  ];
  if (missing.length)
    throw new UsageError(usageLine, prog, `the following arguments are required: ${missing.join(', ')}`);
  let next = 0;
  for (const spec of specs) {
    if (!spec.nargs) values[spec.dest] = positionals[next++];
    else if (spec.nargs === '?')
      values[spec.dest] = positionals[next] !== undefined ? positionals[next++] : (spec.default ?? null);
    else {
      values[spec.dest] = positionals.slice(next);
      next = positionals.length;
    }
  }
  unknown.push(...positionals.slice(next));
  if (unknown.length) throw new UsageError(topUsage, topProg, `unrecognized arguments: ${unknown.join(' ')}`);
}
