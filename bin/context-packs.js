#!/usr/bin/env node
// Runs the CLI as tsc compiled it into dist/ when the package was packed, since Node won't run TypeScript from
// node_modules.
import '../dist/cli.js';
