/** What each kind of finding means, and what the user decides about one, as the agent going through them reads it. */
import fs from 'node:fs';
import path from 'node:path';

import { ROOT } from '../src/root.ts';

const KINDS = path.join(ROOT, 'review', 'prompts', 'kinds');

/** The text for a kind, from its file, named for the kind with a hyphen for each space, such as uncovered-choice.md. */
export function kindText(kind: string): string {
  return fs.readFileSync(path.join(KINDS, `${kind.replaceAll(' ', '-')}.md`), 'utf8').trimEnd();
}

/** The kind with its article, such as "an uncovered choice". */
export function aKind(kind: string): string {
  return `${/^[aeiou]/.test(kind) ? 'an' : 'a'} ${kind}`;
}
