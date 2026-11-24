#!/usr/bin/env node
/**
 * The review's wizard, which an agent runs one step at a time. Each command does the step's deterministic work, keeps
 * what it learned in the run folder, and prints what to do next, with every command to run in full. The orchestrator
 * starts the finders it names, each finder works through its unit with the commands its brief gives, and the wizard
 * refuses an answer until it's whole. A local review and a CI review run the same steps.
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { type Parser, parse, usageError, usageOf, type Values } from '../src/argparse.ts';
import { instructions, region } from '../src/blocks.ts';
import { runAsScript } from '../src/main.ts';
import { exists } from '../src/paths.ts';
import { dumps } from '../src/pyjson.ts';
import { format, quote, repr } from '../src/pystr.ts';
import { ROOT } from '../src/root.ts';
import { Stop } from '../src/stop.ts';
import { units as tableUnits } from '../src/tables.ts';
import { Change, commit, git, Refused } from './change.ts';
import { type Finding, findingsIn, Rejected } from './report.ts';
import { errors, findingsSchema, groupsSchema, type Schema } from './schema.ts';

// The prompts and the schema live with the pack-findings skill, since an installed skill holds only its own folder.
const PROMPTS = path.join(ROOT, 'skills', 'pack-findings');
const STATE = 'state.json';
// The kinds of finding, in the order the findings schema lists them.
const KINDS = findingsSchema().properties!.findings!.items!.properties!.kind!.enum as string[];

interface State {
  readonly base: string;
  readonly head: string;
  readonly root: string;
  readonly command: string;
  readonly units: string[][];
  readonly answers: string;
}

function counted(count: number, noun: string): string {
  return `${count} ${noun}${count !== 1 ? 's' : ''}`;
}

function print(text: string, end = '\n'): void {
  process.stdout.write(text + end);
}

/** A review in progress, kept in its run folder. */
class Run {
  readonly folder: string;
  readonly state: State;

  constructor(folder: string) {
    this.folder = folder;
    if (!exists(path.join(folder, STATE))) {
      throw new Refused(
        `There's no review run in ${folder}: its folder is gone, or init never made it. Start a new ` +
          'review with init.',
      );
    }
    this.state = JSON.parse(fs.readFileSync(path.join(folder, STATE), 'utf8'));
    // git reads the repo the review started in, wherever the agent runs the step from.
    process.chdir(this.state.root);
  }

  change(): Change {
    return new Change(this.state.base, this.state.head);
  }

  /** A command as an agent runs it: the launcher this run was started with, its folder, and the step. */
  command(...args: string[]): string {
    return [this.state.command, '--run', quote(this.folder), ...args].join(' ');
  }

  /** Where an agent writes one of this run's answers, such as unit-1.json, in the run's answers folder. */
  answer(name: string): string {
    return path.join(this.state.answers, name);
  }

  get units(): string[][] {
    return this.state.units;
  }

  /** The uncovered finder's number, which comes after every unit's. */
  get uncovered(): number {
    return this.units.length;
  }

  /** The finder a number names, once init named it. */
  finder(text: string): number {
    if (!/^\d+$/.test(text) || Number(text) > this.uncovered) {
      throw new Refused(`There is no finder ${text}: init named finders 0 to ${this.uncovered}.`);
    }
    return Number(text);
  }

  /**
   * The folder that marks which of a unit's docs doc printed, one empty file for each, so finders running at once
   * never write the same file.
   */
  served(unit: number): string {
    return path.join(this.folder, 'served', `unit-${unit}`);
  }

  /** The review's findings, which submit-groups writes from the groups, so it marks that the run is done. */
  get findings(): string {
    return path.join(this.folder, 'findings.json');
  }

  /** The finders' findings, numbered for the merge. next writes it once every finder is in, so it marks that the merge has started. */
  get sources(): string {
    return path.join(this.folder, 'sources.json');
  }

  /**
   * Which step the run is at: 'finders' until next starts the merge, 'merge' until submit-groups builds the findings,
   * then 'done'. Each phase starts when the file that marks it is written, so this is the one place that knows which
   * file that is.
   */
  phase(): 'finders' | 'merge' | 'done' {
    if (exists(this.findings)) return 'done';
    return exists(this.sources) ? 'merge' : 'finders';
  }

  /** Where submit keeps a finder's answer once it took it, so a later edit to the answer changes nothing. */
  accepted(finder: number): string {
    return path.join(this.folder, 'accepted', `unit-${finder}.json`);
  }

  /** Each finder's number, its label, and the one-line prompt the orchestrator gives it. */
  finders(): [number, string, string][] {
    const labels = [this.units[0]![0]!, ...this.units.slice(1).map((unit) => counted(unit.length, 'doc'))];
    const named: [number, string][] = labels.map((label, n) => [n, `unit ${n}, ${label}`]);
    named.push([this.uncovered, 'the uncovered finder']);
    return named.map(([n, label]) => [
      n,
      label,
      `Run \`${this.command('brief', String(n))}\` and follow what it says.`,
    ]);
  }
}

/** A prompt file filled in as str.format fills it. */
function prompt(name: string, values: Readonly<Record<string, string>>): string {
  return format(fs.readFileSync(path.join(PROMPTS, name), 'utf8'), values);
}

function init(args: Values): void {
  const head = commit(String(args.head));
  if (git('rev-parse', 'HEAD').trim() !== head) {
    throw new Refused(`The checkout isn't the head, ${head}. Check out the head, then run init again.`);
  }
  const root = git('rev-parse', '--show-toplevel').trim();
  const file = instructions(root);
  const units = [[path.relative(root, file)], ...tableUnits(root, region(root, file).block)];
  const change = new Change(String(args.base), head);
  if (!change.paths().length) {
    throw new Refused(`The change from ${args.base} to ${args.head} touches no files, so there is nothing to review.`);
  }
  const commits = git('rev-list', `${change.start}..${change.head}`).split(/\s+/).filter(Boolean).length;
  // Agents write their answers in a folder of their own, so a run folder, which holds what the wizard checked, is
  // never one they can write in. A CI review allows writes in pack-review-answers alone, before the agent starts.
  const temp = os.tmpdir();
  fs.mkdirSync(path.join(temp, 'pack-review-runs'), { recursive: true });
  const folder = fs.mkdtempSync(path.join(temp, 'pack-review-runs', 'pack-review-'));
  const answers = path.join(temp, 'pack-review-answers', path.basename(folder));
  fs.mkdirSync(answers, { recursive: true });
  const state: State = { base: change.base, head: change.head, root, command: String(args.command), units, answers };
  fs.writeFileSync(path.join(folder, STATE), dumps(state), 'utf8');
  const run = new Run(folder);
  const lines = [
    `Reviewing ${counted(commits, 'commit')} that change ${counted(change.paths().length, 'file')}, against ` +
      `${counted(units.length, 'unit')}.`,
    '',
    `Start these ${run.finders().length} subagents now, in the foreground, all in one message, so they run at once ` +
      'and you wait for every answer. Give each exactly this prompt:',
    ...run.finders().map(([, label, line]) => `  ${label}: ${line}`),
    `When all of them have answered, run \`${run.command('next')}\`.`,
  ];
  print(lines.join('\n'));
}

function brief(args: Values): void {
  const run = new Run(String(args.run));
  if (args.finder === 'merge') {
    mergeBrief(run);
    return;
  }
  const finder = run.finder(String(args.finder));
  const cmd = run.command();
  let name: string;
  let docs: string;
  if (finder === run.uncovered) {
    // The uncovered finder searches every unit's docs for a rule that settles a choice, rather than reading each in
    // full, so it reads them with its own tools.
    name = 'uncovered-prompt.md';
    docs = run.units
      .flat()
      .map((docPath) => `- \`${docPath}\`\n`)
      .join('');
  } else {
    name = 'unit-prompt.md';
    docs = run.units[finder]!.map(
      (docPath, n) => `- \`${docPath}\`: run \`${run.command('doc', String(finder), String(n + 1))}\`\n`,
    ).join('');
  }
  print(
    prompt(name, {
      diff: `what \`${cmd} diff <path>\` prints, one path at a time, for the paths \`${cmd} files\` lists`,
      log: `what \`${cmd} log\` prints`,
      docs: docs.replace(/\n+$/, ''),
      answer: run.answer(`unit-${finder}.json`),
      submit: run.command('submit', String(finder)),
      schema: JSON.stringify(findingsSchema(), null, 1),
    }),
    '',
  );
}

/**
 * Every finder's findings, from the unit-<n>.json answers in folder, numbered as <finder>:<index>, so the merging
 * agent can answer with ids and a script can build each finding from the ones it names.
 */
function sources(folder: string): { id: string; finding: Finding }[] {
  const finder = (name: string) => Number(name.slice('unit-'.length, -'.json'.length));
  const answers = fs
    .readdirSync(folder)
    .filter((name) => /^unit-.*\.json$/.test(name))
    .sort((a, b) => finder(a) - finder(b));
  return answers.flatMap((name) => {
    const found: Finding[] = JSON.parse(fs.readFileSync(path.join(folder, name), 'utf8')).findings;
    return found.map((finding, n) => ({ id: `${finder(name)}:${n}`, finding }));
  });
}

/** The run, once every finder is in and the merge has started. */
function merging(run: Run): Run {
  if (run.phase() === 'finders') {
    throw new Refused(`The merge can't start yet: run \`${run.command('next')}\` to see whose answers aren't in.`);
  }
  return run;
}

function mergeBrief(run: Run): void {
  merging(run);
  print(
    prompt('merge-prompt.md', {
      sources: run.command('sources'),
      files: run.command('files'),
      diff: run.command('diff', '<path>'),
      log: run.command('log'),
      answer: run.answer('groups.json'),
      submit: run.command('submit-groups'),
      schema: JSON.stringify(groupsSchema(), null, 1),
    }),
    '',
  );
}

function sourcesStep(args: Values): void {
  print(fs.readFileSync(merging(new Run(String(args.run))).sources, 'utf8'));
}

function doc(args: Values): void {
  const run = new Run(String(args.run));
  const unit = run.finder(String(args.unit));
  if (unit === run.uncovered) {
    throw new Refused('The uncovered finder has no docs to read through doc: search them in the current folder.');
  }
  const docs = run.units[unit]!;
  const n = String(args.n);
  if (!/^\d+$/.test(n) || Number(n) < 1 || Number(n) > docs.length)
    throw new Refused(`Unit ${unit} has ${counted(docs.length, 'doc')}.`);
  const text = fs.readFileSync(path.join(run.state.root, docs[Number(n) - 1]!), 'utf8');
  fs.mkdirSync(run.served(unit), { recursive: true });
  fs.writeFileSync(path.join(run.served(unit), String(Number(n))), '');
  print(text, '');
}

/** The page a step's argument names, from 1. */
function page(text: string): number {
  if (!/^\d+$/.test(text) || Number(text) < 1) throw new Refused(`${repr(text)} isn't a page: pages count from 1.`);
  return Number(text);
}

function files(args: Values): void {
  print(new Run(String(args.run)).change().changed(), '');
}

function diff(args: Values): void {
  const run = new Run(String(args.run));
  const change = run.change();
  const target = String(args.path);
  if (!change.paths().includes(target))
    throw new Refused(`${target} isn't one of the paths \`${run.command('files')}\` lists.`);
  print(change.diff(target, page(String(args.page))), '');
}

function log(args: Values): void {
  print(new Run(String(args.run)).change().log(page(String(args.page))), '');
}

/**
 * The text of the answer an agent wrote to file, the file its brief named, once it's JSON in the schema's shape. The
 * answer can't be in the command itself: Claude Code refuses a command with a brace before a quote, which every JSON
 * object starts with.
 */
function answer(noun: string, file: string, submit: string, shape: Schema): string {
  const it = noun === 'groups' ? 'them' : 'it';
  const again = `then submit ${it} again with \`${submit}\``;
  if (!exists(file)) {
    throw new Refused(
      `Not taken: there is no ${noun} at ${file}. Write ${it} there as JSON, with your tool for writing ` +
        `files, ${again}.`,
    );
  }
  const text = fs.readFileSync(file, 'utf8');
  let value: unknown;
  try {
    value = JSON.parse(text);
  } catch (error) {
    throw new Refused(`Not taken: your ${noun} isn't JSON: ${(error as Error).message}. Fix ${it}, ${again}.`);
  }
  const broken = errors(value, shape);
  if (broken.length) {
    throw new Refused(
      `Not taken: your ${noun} breaks the schema:\n${broken.map((line) => `  ${line}\n`).join('')}Fix ${it}, ${again}.`,
    );
  }
  return text;
}

function submit(args: Values): void {
  const run = new Run(String(args.run));
  const finder = run.finder(String(args.finder));
  const command = run.command('submit', String(finder));
  if (run.phase() !== 'finders')
    throw new Refused("Not taken: the merge has started, so the finders' answers can't change.");
  if (finder !== run.uncovered) {
    const unread = run.units[finder]!.map((docPath, i): [number, string] => [i + 1, docPath]).filter(
      ([n]) => !exists(path.join(run.served(finder), String(n))),
    );
    if (unread.length) {
      const listed = unread
        .map(([n, docPath]) => `${docPath} through \`${run.command('doc', String(finder), String(n))}\``)
        .join(', ');
      const them = unread.length === 1 ? 'it' : 'them';
      throw new Refused(
        `Not taken: you didn't read ${listed}. Read ${them}, check the diff against ${them}, update ` +
          `your answer, then submit it again with \`${command}\`.`,
      );
    }
  }
  const text = answer('answer', run.answer(`unit-${finder}.json`), command, findingsSchema());
  const findings: unknown[] = JSON.parse(text).findings;
  fs.mkdirSync(path.dirname(run.accepted(finder)), { recursive: true });
  fs.writeFileSync(run.accepted(finder), text, 'utf8');
  const name = finder === run.uncovered ? "the uncovered finder's answer" : `unit ${finder}`;
  print(
    `${name[0]!.toUpperCase()}${name.slice(1)} is in, with ${counted(findings.length, 'finding')}. Tell whoever ` +
      `started you that ${name} is in, and stop.`,
  );
}

function nextStep(args: Values): void {
  const run = new Run(String(args.run));
  const phase = run.phase();
  if (phase === 'done') {
    const findings: Finding[] = JSON.parse(fs.readFileSync(run.findings, 'utf8')).findings;
    const kinds = KINDS.filter((kind) => findings.some((found) => found.kind === kind)).map((kind) =>
      counted(findings.filter((found) => found.kind === kind).length, kind),
    );
    const listed = kinds.length ? kinds.slice(0, -1).join(', ') + (kinds.length > 1 ? ' and ' : '') + kinds.at(-1) : '';
    print(
      `Done: ${counted(findings.length, 'finding')}${listed ? `, ${listed}` : ''}, in ${run.findings}. Here they ` +
        `are:\n${JSON.stringify(findings, null, 1)}`,
    );
    return;
  }
  if (phase === 'merge') {
    print(
      "Waiting on the merge, whose groups aren't in yet. If it stopped without its groups going in, start it " +
        `again in the foreground, with the same prompt: Run \`${run.command('brief', 'merge')}\` and follow what ` +
        `it says. When it has answered, run \`${run.command('next')}\` again.`,
    );
    return;
  }
  const finders = run.finders();
  const waiting = finders.filter(([n]) => !exists(run.accepted(n)));
  if (waiting.length) {
    print(
      [
        `Waiting on ${counted(waiting.length, 'finder')}, whose answers aren't in yet:`,
        ...waiting.map(([, label, line]) => `  ${label}: ${line}`),
        'If one of them stopped without its answer going in, start it again in the foreground, with the same prompt. ' +
          `When they have all answered, run \`${run.command('next')}\` again.`,
      ].join('\n'),
    );
    return;
  }
  const found = sources(path.dirname(run.accepted(0)));
  fs.writeFileSync(run.sources, dumps(found), 'utf8');
  print(
    `All ${finders.length} finders are in, with ${counted(found.length, 'finding')}.\n` +
      'Start one subagent in the foreground, with exactly this prompt: ' +
      `Run \`${run.command('brief', 'merge')}\` and follow what it says.\n` +
      `When it has answered, run \`${run.command('next')}\`.`,
  );
}

function submitGroups(args: Values): void {
  const run = new Run(String(args.run));
  if (run.phase() === 'finders') {
    throw new Refused(
      `Not taken: the merge hasn't started. Run \`${run.command('next')}\` to see whose answers aren't in.`,
    );
  }
  const command = run.command('submit-groups');
  const groups = path.join(run.folder, 'groups.json');
  fs.writeFileSync(groups, answer('groups', run.answer('groups.json'), command, groupsSchema()), 'utf8');
  let findings: Finding[];
  try {
    findings = findingsIn(groups, run.sources);
  } catch (error) {
    if (!(error instanceof Rejected)) throw error;
    throw new Refused(`Not taken: ${error.message}. Fix your groups, then submit them again with \`${command}\`.`);
  }
  const built = { base: run.state.base, head: run.state.head, findings };
  fs.writeFileSync(run.findings, dumps(built), 'utf8');
  print(`${counted(findings.length, 'finding')} are in ${run.findings}. Tell whoever started you, and stop.`);
}

const PARSER: Parser = {
  prog: 'review',
  help: '',
  commandRequired: true,
  commandDest: 'step',
  description: "The review's wizard, which an agent runs one step at a time.",
  options: [{ flag: '--run', dest: 'run', metavar: 'RUN', help: 'the run folder init made' }],
  commands: {
    init: {
      help: 'start a review of a change, in a new run folder',
      options: [
        {
          flag: '--base',
          dest: 'base',
          metavar: 'BASE',
          required: true,
          help: 'the commit or branch the change starts from',
        },
        {
          flag: '--head',
          dest: 'head',
          metavar: 'HEAD',
          required: true,
          help: 'the commit or branch that is reviewed, checked out',
        },
        {
          flag: '--command',
          dest: 'command',
          metavar: 'COMMAND',
          required: true,
          help: 'how an agent runs the wizard, ' + 'such as "npx context-packs@0.11.0 review"',
        },
      ],
    },
    brief: {
      help: "print one finder's prompt",
      positionals: [{ dest: 'finder', help: "the finder's number, as init lists them, or merge" }],
    },
    doc: {
      help: "print one of a unit's docs",
      positionals: [
        { dest: 'unit', help: "the unit's number" },
        { dest: 'n', help: "the doc's number in the unit's brief" },
      ],
    },
    files: { help: 'list the paths the change touches' },
    diff: {
      help: "print one path's diff, numbered",
      positionals: [
        { dest: 'path', help: 'a path files lists' },
        { dest: 'page', nargs: '?', default: '1', help: 'which page, from 1' },
      ],
    },
    log: {
      help: "print the change's commits",
      positionals: [{ dest: 'page', nargs: '?', default: '1', help: 'which page, from 1' }],
    },
    submit: {
      help: 'check the answer its brief named and take it',
      positionals: [{ dest: 'finder', help: "the finder's number" }],
    },
    next: { help: 'print what to do now' },
    sources: { help: "print the finders' findings, numbered for the merge" },
    'submit-groups': { help: "check the merging agent's groups and build the findings" },
  },
};

const STEPS: Readonly<Record<string, (args: Values) => void>> = {
  init,
  brief,
  doc,
  files,
  diff,
  log,
  submit,
  next: nextStep,
  sources: sourcesStep,
  'submit-groups': submitGroups,
};

export function main(argv: readonly string[]): void {
  const args = parse(PARSER, argv);
  const step = String(args.step);
  if (step !== 'init' && !args.run)
    usageError(usageOf(PARSER), 'review', `${step} needs --run, the run folder init made`);
  try {
    STEPS[step]!(args);
  } catch (error) {
    // No `pack-review: ` prefix, unlike the review's other scripts: a refusal is the agent's next instruction, so its
    // first word should be what to do.
    if (!(error instanceof Refused) && !(error instanceof Stop)) throw error;
    process.stderr.write(`${error.message}\n`);
    process.exitCode = 1;
  }
}

if (runAsScript(import.meta.filename)) main(process.argv.slice(2));
