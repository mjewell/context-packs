/** The review's prompt files, in review/prompts/, and how to read one. Every module that reads them goes through here. */
import fs from 'node:fs';
import path from 'node:path';
import { format } from '../src/pystr.ts';
import { ROOT } from '../src/root.ts';

export const PROMPTS = path.join(ROOT, 'review', 'prompts');

/**
 * A prompt file, by its path in review/prompts/, filled in as str.format fills it. A file with nothing to fill takes
 * no values, and a placeholder in it stops the step, rather than passing through as text.
 */
export function prompt(name: string, values: Readonly<Record<string, string>>): string {
  return format(fs.readFileSync(path.join(PROMPTS, name), 'utf8'), values);
}
