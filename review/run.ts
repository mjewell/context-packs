/**
 * A review's run folder, which holds what the wizard learned. Which files it holds is the run's state: every step reads
 * it, and none stores it apart.
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { exists } from '../src/paths.ts';
import { dumps } from '../src/pyjson.ts';
import { quote } from '../src/pystr.ts';
import { Change, Refused } from './change.ts';
import type { CiFinding } from './ci_summary.ts';
import type { Finding, Source } from './report.ts';

const STATE = 'state.json';

/** A finding in a run's findings: a local run's have no thread or commentary, and from-pr's have them from CI. */
export type RunFinding = Finding & Partial<CiFinding>;

export interface State {
  readonly base: string;
  readonly head: string;
  readonly root: string;
  readonly command: string;
  readonly units: string[][];
  readonly answers: string;
}

/** A count and its noun, such as "1 doc" or "3 findings": every step's output and the finders' labels use it. */
export function counted(count: number, noun: string): string {
  return `${count} ${noun}${count !== 1 ? 's' : ''}`;
}

/**
 * Write text to file whole or not at all, by renaming a file written beside it. The run's state is which files exist,
 * such as a finder's accepted answer or the file that starts a phase, so a write cut short must never leave one.
 * Every such file goes through here.
 */
function publish(file: string, text: string): void {
  // Each process names its own, so two steps writing one file at once, such as a doc read twice, don't share it.
  const partial = `${file}.${process.pid}.partial`;
  fs.writeFileSync(partial, text, 'utf8');
  fs.renameSync(partial, file);
}

/** A review in progress, kept in its run folder. */
export class Run {
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
  #served(unit: number): string {
    return path.join(this.folder, 'served', `unit-${unit}`);
  }

  /**
   * The text of a unit's doc, by its number in the unit's brief, from 1, once it's marked served. Marking it here is
   * what lets submit check that every doc was read, so no step prints a doc without it.
   */
  serve(unit: number, n: string): string {
    if (unit === this.uncovered) {
      throw new Refused('The uncovered finder has no docs to read through doc: search them in the current folder.');
    }
    const docs = this.units[unit]!;
    if (!/^\d+$/.test(n) || Number(n) < 1 || Number(n) > docs.length)
      throw new Refused(`Unit ${unit} has ${counted(docs.length, 'doc')}.`);
    const text = fs.readFileSync(path.join(this.state.root, docs[Number(n) - 1]!), 'utf8');
    fs.mkdirSync(this.#served(unit), { recursive: true });
    publish(path.join(this.#served(unit), String(Number(n))), '');
    return text;
  }

  /** The unit's docs that doc hasn't printed yet, each with its number in the unit's brief, from 1. */
  unread(unit: number): [number, string][] {
    return this.units[unit]!.map((docPath, i): [number, string] => [i + 1, docPath]).filter(
      ([n]) => !exists(path.join(this.#served(unit), String(n))),
    );
  }

  /**
   * The file that holds the review's findings, which finish() writes, so it marks that the run is done. Steps name it
   * in what they print, and read the findings through findings().
   */
  get findingsFile(): string {
    return path.join(this.folder, 'findings.json');
  }

  /** Refuses once the findings are built, since a done run never changes. */
  buildingFindings(): void {
    if (this.phase() === 'done') {
      throw new Refused(
        "Not taken: the findings are already built, so the groups can't change. Tell whoever started you, and stop.",
      );
    }
  }

  /**
   * Finish the run with its findings, and the merging agent's groups, their JSON text, when a merge built them. Each
   * path to the findings writes them here, in one shape: a merge, a review that found nothing, and from-pr.
   */
  finish(findings: readonly RunFinding[], groups?: string): void {
    this.buildingFindings();
    if (groups !== undefined) publish(path.join(this.folder, 'groups.json'), groups);
    publish(this.findingsFile, dumps({ base: this.state.base, head: this.state.head, findings }));
  }

  /** The review's findings, once the run is done. */
  findings(): RunFinding[] {
    if (this.phase() !== 'done') {
      throw new Refused(`The review has no findings yet: run \`${this.command('next')}\` to see what it's waiting on.`);
    }
    return JSON.parse(fs.readFileSync(this.findingsFile, 'utf8')).findings;
  }

  /** The finders' findings, numbered for the merge. startMerge() writes it, so it marks that the merge has started. */
  get #sourcesFile(): string {
    return path.join(this.folder, 'sources.json');
  }

  /**
   * Which step the run is at: 'finders' until next starts the merge, 'merge' until submit-groups builds the findings,
   * then 'done'. With no findings to merge, next builds them, and the run goes from 'finders' to 'done'. Each phase
   * starts when the file that marks it is written, so this is the one place that knows which file that is.
   */
  phase(): 'finders' | 'merge' | 'done' {
    if (exists(this.findingsFile)) return 'done';
    return exists(this.#sourcesFile) ? 'merge' : 'finders';
  }

  /** Where submit keeps a finder's answer once it took it, so a later edit to the answer changes nothing. */
  #accepted(finder: number): string {
    return path.join(this.folder, 'accepted', `unit-${finder}.json`);
  }

  /** Refuses once every finder is in, since the merge reads their answers from then on. */
  takingAnswers(): void {
    if (this.phase() !== 'finders')
      throw new Refused("Not taken: every finder is in, so the finders' answers can't change.");
  }

  /** Keep a finder's answer, its checked JSON text, while the finders' answers can still change. */
  accept(finder: number, text: string): void {
    this.takingAnswers();
    fs.mkdirSync(path.dirname(this.#accepted(finder)), { recursive: true });
    publish(this.#accepted(finder), text);
  }

  /** The finders whose answers aren't in, as finders() lists them. */
  waiting(): [number, string, string][] {
    return this.finders().filter(([n]) => !exists(this.#accepted(n)));
  }

  /**
   * Start the merge, once every finder is in: number every finder's findings as <finder>:<index>, so the merging agent
   * can answer with ids and a script can build each finding from the ones it names.
   */
  startMerge(): Source[] {
    const found = this.finders().flatMap(([finder]) => {
      const findings: Finding[] = JSON.parse(fs.readFileSync(this.#accepted(finder), 'utf8')).findings;
      return findings.map((finding, n) => ({ id: `${finder}:${n}`, finding }));
    });
    publish(this.#sourcesFile, dumps(found));
    return found;
  }

  /** Refuses until the merge has started. */
  merging(): void {
    if (this.phase() === 'finders') {
      throw new Refused(`The merge can't start yet: run \`${this.command('next')}\` to see whose answers aren't in.`);
    }
  }

  /** The finders' findings, as startMerge() numbered them, once the merge has started. */
  sources(): Source[] {
    this.merging();
    return JSON.parse(fs.readFileSync(this.#sourcesFile, 'utf8'));
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

/** A new run folder holding state, and the answers folder beside it. */
export function newRun(state: Omit<State, 'answers'>): Run {
  // Agents write their answers in a folder of their own, so a run folder, which holds what the wizard checked, is
  // never one they can write in. A CI review allows writes in pack-review-answers alone, before the agent starts.
  const temp = os.tmpdir();
  fs.mkdirSync(path.join(temp, 'pack-review-runs'), { recursive: true });
  const folder = fs.mkdtempSync(path.join(temp, 'pack-review-runs', 'pack-review-'));
  const answers = path.join(temp, 'pack-review-answers', path.basename(folder));
  fs.mkdirSync(answers, { recursive: true });
  publish(path.join(folder, STATE), dumps({ ...state, answers }));
  return new Run(folder);
}
