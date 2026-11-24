/**
 * Stands in for `claude -p` in tests. Reads the instructions file in its working directory, as Claude Code loads it,
 * and "reads" the doc of each table row whose when appears in the prompt, following rows in what it reads, writing
 * each read as a tool_use line of stream-json, the way the real command does. Appends its arguments, working
 * directory, the files in it and the instructions file it loaded to $FAKE_CLAUDE_LOG.
 *
 * It sets process.exitCode rather than calling process.exit, since an exit can cut off what it printed to a pipe.
 */
import fs from 'node:fs';
import path from 'node:path';

const ROW = /^\| (.+?) \| `(.+?)` \|$/gm;

function print(event: unknown): void {
  process.stdout.write(`${JSON.stringify(event)}\n`);
}

function main(): void {
  const args = process.argv.slice(2);
  const prompt = args[args.indexOf('-p') + 1]!;
  const cwd = process.cwd();
  const instructions = path.join(cwd, 'CLAUDE.md');
  const loaded = fs.existsSync(instructions) ? fs.readFileSync(instructions, 'utf8') : '';
  const log = process.env.FAKE_CLAUDE_LOG;
  if (log) {
    // Every file and folder under cwd, as pathlib's rglob('*') lists them.
    const files = (fs.readdirSync(cwd, { recursive: true }) as string[]).map((f) => f.split(path.sep).join('/'));
    fs.appendFileSync(log, `${JSON.stringify({ args, cwd, instructions: loaded, files: files.sort() })}\n`);
  }
  print({ type: 'system', subtype: 'init' });
  const crash = process.env.FAKE_CLAUDE_CRASH;
  if (crash) {
    // As a process that dies with a message, such as Node's on an uncaught error.
    process.stderr.write(`${crash}\n`);
    process.exitCode = 1;
    return;
  }
  const error = process.env.FAKE_CLAUDE_ERROR;
  if (error) {
    // As the real command fails on a model it can't use: before any tool, with is_error but subtype success.
    print({ type: 'assistant', message: { content: [{ type: 'text', text: error }] } });
    print({ type: 'result', subtype: 'success', is_error: true, result: error });
    process.exitCode = 1;
    return;
  }
  const seen = new Set<string>();

  // Read the doc of each row whose when the prompt contains, and the rows of each one read, as an agent follows a
  // row to a pack's index.
  const follow = (text: string): void => {
    for (const [, when, file] of text.matchAll(ROW)) {
      const target = path.isAbsolute(file!) ? file! : path.join(cwd, file!);
      if (prompt.toLowerCase().includes(when!.toLowerCase()) && !seen.has(target)) {
        seen.add(target);
        print({
          type: 'assistant',
          message: { content: [{ type: 'tool_use', id: 'toolu_1', name: 'Read', input: { file_path: target } }] },
        });
        if (fs.statSync(target, { throwIfNoEntry: false })?.isFile()) follow(fs.readFileSync(target, 'utf8'));
      }
    }
  };

  follow(loaded);
  if (process.env.FAKE_CLAUDE_MAX_TURNS) {
    // As the real command ends a session that runs out of turns: flagged is_error, with no result.
    print({ type: 'result', subtype: 'error_max_turns', is_error: true });
    process.exitCode = 1;
    return;
  }
  print({ type: 'result', subtype: 'success', result: 'Done.', total_cost_usd: 0.0123 });
}

main();
