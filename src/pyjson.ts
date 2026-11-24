/**
 * JSON written the way Python's json.dumps(value, ensure_ascii=False) writes it, for text people and tests read: ", "
 * between items and ": " after a key, where JSON.stringify writes "," and ":". With indent, the two write the same.
 */
/** value as json.dumps(value) writes it with ensure_ascii, its default: every character past ASCII as a \u escape. */
export function ascii(json: string): string {
  return json.replace(/[\u0080-\uffff]/g, (c) => `\\u${c.charCodeAt(0).toString(16).padStart(4, '0')}`);
}

export function dumps(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(dumps).join(', ')}]`;
  if (value !== null && typeof value === 'object') {
    return `{${Object.entries(value)
      .map(([key, item]) => `${JSON.stringify(key)}: ${dumps(item)}`)
      .join(', ')}}`;
  }
  return JSON.stringify(value) ?? 'null';
}
