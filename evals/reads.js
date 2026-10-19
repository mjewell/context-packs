// A promptfoo assertion: whether an agent's run read the context docs a case expects. A case names a doc by the end of
// its path, such as testing.md or core/testing.md, in vars.reads, or in vars.skips for a doc it must not read, each
// comma-separated. With neither, it must read no doc: a Markdown file under a folder named vars.docs,
// context-packs/ unless the case says otherwise, such as packs/core/ for a pack kept outside context-packs/.
const names = (value) => (value ?? '').split(',').map((name) => name.trim()).filter(Boolean);

// The doc's path from the docs folder on, such as context-packs/gen/core/testing.md, or null for a file that isn't one.
const doc = (path, folder) => {
  if (!path.endsWith('.md')) return null;
  if (path.startsWith(folder)) return path;
  const at = path.indexOf(`/${folder}`);
  return at === -1 ? null : path.slice(at + 1);
};

const matches = (path, name) => path === name || path.endsWith(`/${name}`);

module.exports = (output, context) => {
  const read = (context.providerResponse?.metadata?.toolCalls ?? [])
    .filter((call) => call.name === 'Read')
    .map((call) => call.input?.file_path ?? '');
  const wasRead = (name) => read.some((path) => matches(path, name));
  const missing = names(context.vars.reads).filter((name) => !wasRead(name));
  const expectsAny = names(context.vars.reads).length || names(context.vars.skips).length;
  const docs = [...new Set(read.map((path) => doc(path, context.vars.docs || 'context-packs/')).filter(Boolean))];
  const unwanted = expectsAny ? names(context.vars.skips).filter(wasRead) : docs;
  const pass = missing.length === 0 && unwanted.length === 0;
  const problems = [...missing.length ? [`missing: ${missing.join(', ')}`] : [],
    ...unwanted.length ? [`shouldn't have read: ${unwanted.join(', ')}`] : []];
  return { pass, score: pass ? 1 : 0, reason: [`read: ${docs.join(', ') || 'no docs'}`, ...problems].join('; ') };
};
