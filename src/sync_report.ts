/** What a sync changed, in lines for the person who ran it. */
import type { Region } from './blocks.ts';
import type { Import } from './imports.ts';
import { COMMIT } from './origins.ts';

/** ref as git shows it: a commit abbreviated, a tag in full. */
function short(ref: string): string {
  return COMMIT.test(ref) ? ref.slice(0, 7) : ref;
}

/** Where the import pack pins its pack, or nothing for a local one, which syncs from its working tree. */
function at(imported: Import): string {
  return imported.ref ? ` @ ${short(imported.ref)}` : '';
}

/**
 * Lines describing what the sync did: whether it created AGENTS.md and linked CLAUDE.md to it, how the import packs
 * before it became the ones after, where each pinned pack in updating stayed, and otherwise whether the block it found
 * differs from the one it wrote.
 */
export function changes(
  found: Region,
  written: string,
  created: boolean,
  linked: boolean,
  before: readonly Import[],
  after: readonly Import[],
  updating: readonly string[] = [],
): string[] {
  const was = new Map(before.map((i) => [i.id, i]));
  const now = new Map(after.map((i) => [i.id, i]));
  const lines = [...(created ? ['Created AGENTS.md'] : []), ...(linked ? ['Linked CLAUDE.md to AGENTS.md'] : [])];
  let kept = 0;
  for (const [id, imported] of now) {
    const old = was.get(id);
    if (!old) {
      lines.push(`${id}: added${at(imported)}`);
    } else if (old.ref !== imported.ref) {
      lines.push(`${id}: ${short(old.ref!)} → ${short(imported.ref!)}`);
    } else if (updating.includes(id) && imported.ref) {
      kept += 1;
      lines.push(`${id}: ${short(imported.ref)} (${COMMIT.test(imported.ref) ? 'up to date' : 'tag'})`);
    }
  }
  lines.push(...[...was.keys()].filter((id) => !now.has(id)).map((id) => `${id}: removed`));
  if (lines.length === kept && found.block !== written) lines.push('Updated the context-packs block');
  if (lines.length) return lines;
  const pins = after.map((i) => i.id + at(i));
  return [pins.length ? `Nothing changed: ${pins.join(', ')}` : 'Nothing changed'];
}
