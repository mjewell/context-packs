/** Where the repo, or the npm package, is on disk. */
import path from 'node:path';

/**
 * The folder holding src/ and review/. Every module sits one folder below it, or two in the npm package, where tsc
 * writes each module's .js into dist/.
 */
export const ROOT = path.resolve(import.meta.dirname, import.meta.filename.endsWith('.js') ? '../..' : '..');
