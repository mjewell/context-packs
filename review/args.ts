/**
 * The claude_args the review hands claude-code-action, as one line. The reviewer runs the pack-findings skill, whose
 * wizard starts the finders and the merge. claude-code-action splits the line the way a shell would. output() writes a
 * prompt or a claude_args line as a GitHub step output.
 */
import { randomUUID } from 'node:crypto';
import fs from 'node:fs';

import { quote } from '../src/pystr.ts';
import { ROOT } from '../src/root.ts';
import { fail } from '../src/stop.ts';

/**
 * The values as one claude_args line, each quoted whole. A value holding a single quote stops the run, since
 * claude-code-action may split it.
 */
export function line(values: readonly string[]): string {
  const quoted = values.filter((value) => value.includes("'"));
  if (quoted.length) {
    fail(`pack-review: these arguments hold a single quote, which claude-code-action may split: ${quoted.join(', ')}`);
  }
  return values.map(quote).join(' ');
}

/** Write a step output, under a delimiter the value can't hold. */
export function output(name: string, value: string): void {
  const delimiter = `EOF_${randomUUID().replaceAll('-', '')}`;
  if (value.includes(delimiter)) throw new Error(`the ${name} output holds its own delimiter`);
  fs.appendFileSync(process.env.GITHUB_OUTPUT!, `${name}<<${delimiter}\n${value}\n${delimiter}\n`, 'utf8');
}

/**
 * The review agent's line: it runs the pack-findings skill, as a local review does, from this checkout of the review,
 * with this checkout's CLI. It may run only the commands the skill runs, and has no MCP server. It writes only in
 * answers, the folder where the wizard's briefs say to write each answer.
 */
export function reviewer(answers: string, model: string): string {
  // The path the skill builds from its own folder, so the agent's commands match it.
  const cli = `node ${ROOT}/src/cli.ts`;
  // git rev-parse and git status have no option that writes a file, unlike git log's --output.
  const allowed = [
    'Skill(context-packs:pack-findings)', `Bash(${cli} review:*)`, `Bash(${cli} docs)`, 'Bash(git rev-parse:*)',
    'Bash(git status:*)',
    // A headless run writes outside its working directory only with both this rule and --add-dir. The rule's //
    // makes the path absolute, where one / would start from the settings file.
    `Edit(/${answers}/**)`,
  ];
  return line([
    '--plugin-dir', ROOT, '--add-dir', answers, '--tools', 'Read,Glob,Grep,Write,Bash,Agent,Skill',
    '--allowedTools', allowed.join(','), '--disallowedTools', 'Read(./.git/**)', ...(model ? ['--model', model] : []),
    '--restricted', '--strict-mcp-config',
  ]);
}
