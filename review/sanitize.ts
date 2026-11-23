/**
 * Remove invisible characters from the review agent's findings, and redact secrets, before they're posted. The
 * findings appear only in the summary's JSON code block, where every other character shows as written, so people and
 * the author's local run see the same text.
 */
export const SECRETS = /sk-ant-[A-Za-z0-9_-]+|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}/g;

export function clean(text: string): string {
  return text.replace(/\p{Cf}/gu, '').replace(SECRETS, '[redacted]').trim();
}
