import type { TestContext } from 'node:test';

/**
 * What a test runs in, such as a temp repo. Each case class sets itself up in setUp, calling super.setUp() first, and
 * a suite that needs more subclasses the case and adds to setUp. A test gets its case from `await XCase.make(t)`,
 * and whatever setUp made through t, such as a temp folder, goes when the test ends.
 */
export class Case {
  protected readonly t: TestContext;

  constructor(t: TestContext) {
    this.t = t;
  }

  /** A case of this class, set up for the test t. */
  static async make<C extends Case>(this: new (t: TestContext) => C, t: TestContext): Promise<C> {
    const c = new this(t);
    await c.setUp();
    return c;
  }

  protected async setUp(): Promise<void> {}
}
