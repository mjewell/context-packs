/** Assertions node:assert lacks, each failing with both texts in full. */
import assert from 'node:assert/strict';

/** Fails unless text holds part. */
export function includes(text: string, part: string, message?: string): void {
  if (!text.includes(part)) {
    assert.fail(`${message ? `${message}: ` : ''}expected ${JSON.stringify(part)} in:\n${text}`);
  }
}

/** Fails if text holds part. */
export function excludes(text: string, part: string, message?: string): void {
  if (text.includes(part)) {
    assert.fail(`${message ? `${message}: ` : ''}expected no ${JSON.stringify(part)} in:\n${text}`);
  }
}

/** Fails unless the script exited with code, showing what it printed as an error. */
export function exits(result: { readonly status: number | null; readonly stderr: string }, code: number): void {
  assert.equal(result.status, code, result.stderr);
}
