#!/usr/bin/env node
/**
 * Write the review job's prompt and claude_args as step outputs. Its agent runs the pack-findings skill on the
 * reviewed range, as a local review does, so both run the wizard the same way. It asks for the checkout CLI, so the
 * wizard is the pinned commit's, like the rest of the review's code.
 */
import { parse } from '../src/argparse.ts';
import { Stop } from '../src/stop.ts';
import { output, reviewer } from './args.ts';

const args = parse(
  {
    prog: 'start.ts',
    help: '',
    options: [
      {
        flag: '--base',
        dest: 'base',
        metavar: 'BASE',
        required: true,
        help: 'the commit the reviewed change starts from',
      },
      { flag: '--head', dest: 'head', metavar: 'HEAD', required: true, help: 'the commit that is reviewed' },
      {
        flag: '--answers',
        dest: 'answers',
        metavar: 'ANSWERS',
        required: true,
        help: "the wizard's pack-review-answers " + 'folder, the one place the agent may write, made already',
      },
      {
        flag: '--model',
        dest: 'model',
        metavar: 'MODEL',
        default: '',
        help: 'the model to review with, if not Claude ' + "Code's default",
      },
    ],
  },
  process.argv.slice(2),
) as Record<string, string>;
try {
  output(
    'prompt',
    `Use the pack-findings skill on the commit range ${args.base}..${args.head}, with the checkout CLI.`,
  );
  output('claude-args', reviewer(args.answers!, args.model!));
} catch (error) {
  if (!(error instanceof Stop)) throw error;
  process.stderr.write(`${error.message}\n`);
  process.exit(error.code);
}
