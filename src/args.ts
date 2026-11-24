/** The CLI's arguments. */
import { type Parser, parse as parseArgs, usageError } from './argparse.ts';
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

const PARSER: Parser = {
  prog: 'context-packs',
  help: '',
  description:
    'Sync context packs into a repository, or any folder such as the one above the repositories: the ' +
    "packs in context-packs/, the repo's own and those its import packs name, as one block in AGENTS.md, with the " +
    'docs of packs from git and the indexes of nested packs in context-packs/gen/. Leave out the command to resync ' +
    'every pack at its pinned ref.',
  options: [{ flag: '--dir', dest: 'dir', metavar: 'DIR', help: 'the folder to sync, if not the current one' }],
  commands: {
    add: {
      help:
        "install a pack as an import pack in context-packs/<id>/: one from git pinned to its origin's latest " +
        'commit or to --ref, or a folder on disk read where it is',
      positionals: [
        {
          dest: 'id',
          help: 'the folder under context-packs/ to put the import pack in, such as core or ' + 'project/typescript',
        },
        { dest: 'origin', help: 'a git URL, or the path of a folder on disk, such as docs/agents or ../agent-config' },
      ],
      options: [
        {
          flag: '--path',
          dest: 'path',
          metavar: 'PATH',
          default: '',
          help: 'the folder in the origin holding the ' + 'pack, if not its root',
        },
        { flag: '--ref', dest: 'ref', metavar: 'REF', help: 'a tag or commit to pin a pack from git to' },
        {
          flag: '--when',
          dest: 'when',
          metavar: 'WHEN',
          help: "the pack's when, in place of its author's: a row, or " + 'always to inline it',
        },
      ],
    },
    remove: { help: 'uninstall a pack, deleting its import pack', positionals: [{ dest: 'id' }] },
    update: {
      help:
        "move packs pinned to a commit to the tip of their origin's default branch, leaving those pinned to a " + 'tag',
      positionals: [{ dest: 'ids', nargs: '*', help: 'the packs to update; all of them if left out' }],
      options: [
        {
          flag: '--ref',
          dest: 'ref',
          metavar: 'REF',
          help: 'a tag or commit to pin the one named pack to ' + 'instead',
        },
      ],
    },
    list: { help: 'list the import packs, where each comes from, and its pin' },
    check: { help: 'exit 1 if a sync would change anything, writing nothing' },
    docs: {
      help:
        "print the path of every doc and index the packs' tables point at, one per line, with a blank line " +
        'between packs, writing nothing',
    },
    eval: {
      help:
        "run each pack's eval prompts: ones that should, or shouldn't, make an agent read a doc, each as a " +
        'claude -p session with the pack alone',
      positionals: [
        {
          dest: 'docs',
          nargs: '*',
          help:
            'the docs whose cases to run, as eval names them, such as ' +
            'testing.md or core/testing.md; all of them if left out',
        },
      ],
      options: [
        {
          flag: '--pack',
          dest: 'pack',
          metavar: 'PACK',
          help:
            "a pack's folder, relative to the repo, to run only " + 'its prompts, whether the repo installs it or not',
        },
        {
          flag: '--runs',
          dest: 'runs',
          metavar: 'RUNS',
          default: '1',
          help: 'how many times to run each prompt, 1 by ' + 'default',
        },
        {
          flag: '--model',
          dest: 'model',
          metavar: 'MODEL',
          default: 'sonnet',
          help: 'the model the sessions use, ' + 'sonnet by default',
        },
        {
          flag: '--json',
          dest: 'json',
          help:
            'print one JSON document of each prompt and its runs once they finish, ' + 'instead of lines as they go',
        },
      ],
    },
  },
};

/** The CLI's arguments in argv, with the folder to sync defaulting to cwd. */
export function parse(argv: readonly string[], cwd: string): Args {
  const values = parseArgs(PARSER, argv);
  const runs = String(values.runs ?? '1');
  if (!/^\s*[+-]?\d+\s*$/.test(runs)) {
    usageError(
      'usage: context-packs eval [-h] [--pack PACK] [--runs RUNS] [--model MODEL] [--json] [docs ...]',
      'context-packs eval',
      `argument --runs: invalid int value: '${runs}'`,
    );
  }
  return {
    command: null,
    id: '',
    origin: '',
    path: '',
    ref: null,
    when: null,
    ids: [],
    docs: [],
    pack: null,
    model: 'sonnet',
    json: false,
    ...values,
    dir: pathlike(String(values.dir ?? cwd)),
    runs: Number(runs),
  } as Args;
}
