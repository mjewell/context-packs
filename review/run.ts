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

const STATE = 'state.json';

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

/** A new run folder holding state, and the answers folder beside it. */
export function newRun(state: Omit<State, 'answers'>): Run {
  // Agents write their answers in a folder of their own, so a run folder, which holds what the wizard checked, is
  // never one they can write in. A CI review allows writes in pack-review-answers alone, before the agent starts.
  const temp = os.tmpdir();
  fs.mkdirSync(path.join(temp, 'pack-review-runs'), { recursive: true });
  const folder = fs.mkdtempSync(path.join(temp, 'pack-review-runs', 'pack-review-'));
  const answers = path.join(temp, 'pack-review-answers', path.basename(folder));
  fs.mkdirSync(answers, { recursive: true });
  fs.writeFileSync(path.join(folder, STATE), dumps({ ...state, answers }), 'utf8');
  return new Run(folder);
}
