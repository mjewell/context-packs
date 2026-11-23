/** String operations that keep the Python version's results, where JavaScript's differ. */

// Every line boundary str.splitlines splits at, \r\n counted as one.
const BREAKS = /\r\n|[\n\r\v\f\x1c\x1d\x1e\x85\u2028\u2029]/;

/** text's lines, as str.splitlines gives them: without their breaks, and no empty line after a final break. */
export function splitlines(text: string): string[] {
  if (!text) return [];
  const lines = text.split(BREAKS);
  if (lines.at(-1) === '') lines.pop();
  return lines;
}

/** text quoted as Python's repr quotes a string: in single quotes, unless it holds one and no double quote. */
export function repr(text: string): string {
  const escaped = text.replace(/\\/g, '\\\\').replace(/\n/g, '\\n').replace(/\r/g, '\\r').replace(/\t/g, '\\t');
  if (text.includes("'") && !text.includes('"')) return `"${escaped}"`;
  return `'${escaped.replace(/'/g, "\\'")}'`;
}

/** template filled in as str.format fills it: each {name} replaced, and {{ and }} written as one brace. */
export function format(template: string, values: Readonly<Record<string, string>>): string {
  return template.replace(/\{\{|\}\}|\{(\w+)\}/g, (match, key?: string) => {
    if (match === '{{') return '{';
    if (match === '}}') return '}';
    const value = values[key!];
    if (value === undefined) throw new Error(`a template has a placeholder {${key}} that nothing fills`);
    return value;
  });
}

/** text quoted for a POSIX shell, as shlex.quote quotes it: as it is when it holds only safe characters. */
export function quote(text: string): string {
  if (!text) return "''";
  if (/^[\w@%+=:,./-]+$/.test(text)) return text;
  return `'${text.replace(/'/g, `'"'"'`)}'`;
}
