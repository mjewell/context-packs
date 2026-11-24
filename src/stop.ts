/**
 * How a command stops early: with a message for the person who ran it, and exit code 1. It's thrown, not an exit, so
 * every undo and clean-up the stop passes through runs first. main prints the message.
 */
export class Stop extends Error {
  readonly code: number;

  constructor(message: string, code = 1) {
    super(message);
    this.code = code;
  }
}

export function fail(message: string): never {
  throw new Stop(message);
}

/** Runs each clean-up added to it, newest first, when it closes, as Python's ExitStack does. */
export class Stack {
  readonly #cleanups: (() => void)[] = [];

  defer(cleanup: () => void): void {
    this.#cleanups.push(cleanup);
  }

  close(): void {
    while (this.#cleanups.length) this.#cleanups.pop()!();
  }
}
