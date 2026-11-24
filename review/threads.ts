#!/usr/bin/env node
/**
 * Print pack-review's review threads on a PR as JSON, with each comment as trust.ts lets an agent see it. The pairing
 * job runs it, and its agents read the threads from this output, so they need no tools.
 */
import { parse } from '../src/argparse.ts';
import { dumps } from '../src/pyjson.ts';
import { GitHubError } from './github.ts';
import { threads } from './trust.ts';

const args = parse(
  {
    prog: 'threads.ts',
    help: '',
    options: [
      {
        flag: '--pr',
        dest: 'pr',
        metavar: 'PR',
        required: true,
        help: 'the PR number, in the repo GITHUB_REPOSITORY names',
      },
    ],
  },
  process.argv.slice(2),
);
try {
  process.stdout.write(`${dumps(await threads(Number(args.pr)))}\n`);
} catch (error) {
  if (!(error instanceof GitHubError)) throw error;
  process.stderr.write(`pack-review: ${error.message}\n`);
  process.exitCode = 1;
}
