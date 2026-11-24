import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { describe, test } from 'node:test';

import { ROOT } from './scripts.ts';

const NPX = /npx (?:--yes )?context-packs(?:@[\w.-]+)?/g;

/** Each skill runs the CLI version it was written for, so a version published later can't change what it runs. */
describe("the skills' npx pins", () => {
  test('every npx command in a skill pins the packages version', () => {
    const { version } = JSON.parse(fs.readFileSync(path.join(ROOT, 'package.json'), 'utf8'));
    const skills = path.join(ROOT, 'skills');
    const commands = fs
      .readdirSync(skills)
      .sort()
      .map((name) => path.join(skills, name, 'SKILL.md'))
      .filter((file) => fs.existsSync(file))
      .flatMap((file) =>
        [...fs.readFileSync(file, 'utf8').matchAll(NPX)].map((m) => [path.relative(ROOT, file), m[0]] as const),
      );

    assert.ok(commands.length, 'no skill runs npx context-packs');
    assert.deepEqual(
      commands.filter(([, npx]) => !npx.endsWith(`context-packs@${version}`)),
      [],
    );
  });
});
