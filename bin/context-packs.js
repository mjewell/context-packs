#!/usr/bin/env node
// Runs the Python CLI bundled with this package, passing its arguments, output and exit code through.
const { spawnSync } = require('node:child_process');
const path = require('node:path');

const cli = path.join(__dirname, '..', 'src', 'cli.py');
const result = spawnSync('python3', [cli, ...process.argv.slice(2)], { stdio: 'inherit' });
if (result.error) {
  console.error(`context-packs: couldn't run python3 (${result.error.message}). Install Python 3.9 or later.`);
  process.exit(1);
}
process.exit(result.status ?? 1);
