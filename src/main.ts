/** Telling whether a module is the script Node was asked to run, as Python's `__name__ == '__main__'` does. */
import fs from 'node:fs';

/** Whether the module whose import.meta.filename is filename is the script node ran, not one imported. */
export function runAsScript(filename: string): boolean {
  const script = process.argv[1];
  return script !== undefined && fs.realpathSync(script) === filename;
}
