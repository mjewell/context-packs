/**
 * The files a synced folder's tables point an agent at, read from the synced files alone, so listing them fetches no
 * pack from git.
 */
import path from 'node:path';

import { read } from './blocks.ts';
import { base } from './packs.ts';
import { isFile, parts, resolve } from './paths.ts';
import { fail } from './stop.ts';

// A table as tree.table writes it, and the path in each of its rows.
const TABLE = /^\| When \| Read \|\n\|---\|---\|\n((?:\|.*\|\n)*)/gm;
const ROW = /^\| .* \| `([^`]+)` \|$/gm;

/**
 * The paths the block's tables point at, then those the tables in each of those files point at, as the tables show
 * them, grouped by the table they're in. Each table is one pack's, so each group is a unit for a review to check. A
 * nested pack's index holds that pack's own rules, so it starts its own table's group, not its parent's.
 */
export function units(repo: string, block: string): string[][] {
  const start = base(repo);
  // The tables' paths start from the root of the git repo holding the folder, unless they're absolute.
  const up = path.isAbsolute(start) ? 0 : parts(start).length;
  const root = path.resolve(resolve(repo), ...Array<string>(up).fill('..'));
  const found: string[][] = [];
  const seen = new Set<string>();
  const queue: [string | null, string][] = [[null, block]];
  while (queue.length) {
    const [index, text] = queue.shift()!;
    [...text.matchAll(TABLE)].forEach(([, table], n) => {
      const unit = index && n === 0 ? [index] : [];
      for (const [, rowPath] of table!.matchAll(ROW) as IterableIterator<[string, string]>) {
        if (seen.has(rowPath)) continue;
        seen.add(rowPath);
        // resolve, since a row's path is absolute when the tables' paths are.
        const file = path.resolve(root, rowPath);
        if (!isFile(file)) {
          fail(
            `context-packs: a table points at ${rowPath}, which doesn't exist. Run \`npx context-packs\` ` +
              'and commit the result.',
          );
        }
        const content = read(file);
        if (new RegExp(TABLE.source, 'm').test(content)) queue.push([rowPath, content]);
        else unit.push(rowPath);
      }
      if (unit.length) found.push(unit);
    });
  }
  return found;
}
