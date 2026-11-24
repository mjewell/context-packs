/** Shell words as Python's shlex reads and writes them, for the tests that check a command line a step prints. */

/** part as one shell word: as it is when it holds only safe characters, else in single quotes. As shlex.quote. */
export function quote(part: string): string {
  return /^[\w@%+=:,./-]+$/.test(part) ? part : `'${part.replaceAll("'", `'"'"'`)}'`;
}

/** The words of a POSIX shell line, with its quotes and backslashes taken out. As shlex.split. */
export function split(line: string): string[] {
  const words: string[] = [];
  let word: string | null = null;
  for (let i = 0; i < line.length; i++) {
    const c = line[i]!;
    if (c === "'") {
      const end = line.indexOf("'", i + 1);
      if (end < 0) throw new Error('No closing quotation');
      word = (word ?? '') + line.slice(i + 1, end);
      i = end;
    } else if (c === '"') {
      word ??= '';
      for (i++; line[i] !== '"'; i++) {
        if (i >= line.length) throw new Error('No closing quotation');
        if (line[i] === '\\' && '\\"$`\n'.includes(line[i + 1] ?? '')) i++;
        word += line[i];
      }
    } else if (c === '\\') {
      word = (word ?? '') + (line[++i] ?? '');
    } else if (/\s/.test(c)) {
      if (word !== null) words.push(word);
      word = null;
    } else {
      word = (word ?? '') + c;
    }
  }
  if (word !== null) words.push(word);
  return words;
}
