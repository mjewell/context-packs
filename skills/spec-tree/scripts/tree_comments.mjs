// The pure part of a spec tree page's comments, inlined into the page ahead of tree_comments_ui.js and tested under
// node. A comment is { id, path, text }, where path is the source text of each node from the top level down to the
// one commented on. A path names a node by its text, not its position, so a comment stays on its node through a
// re-render that moves other nodes, and an agent can find the node by searching the tree's file for the text.

const keyOf = path => JSON.stringify(path);

// byRow lines up with paths, the page's nodes in order. A comment goes on the first node with its path. One that
// matches no node is an orphan: its node's text or place changed after the comment was left.
export function placeComments(comments, paths) {
  const rowOf = new Map();
  paths.forEach((path, i) => { if (!rowOf.has(keyOf(path))) rowOf.set(keyOf(path), i); });
  const byRow = paths.map(() => []);
  const orphans = [];
  for (const c of comments) {
    const i = rowOf.get(keyOf(c.path));
    if (i === undefined) orphans.push(c);
    else byRow[i].push(c);
  }
  return { byRow, orphans };
}

// The text a person pastes to an agent, numbered across placed comments and then orphans.
export function asMarkdown(file, placed, orphans) {
  let n = 0;
  const item = c => {
    const node = c.path[c.path.length - 1];
    const under = c.path.length > 1 ? `, under ${c.path.slice(0, -1).map(t => `"${t}"`).join(' > ')}` : '';
    const body = c.text.split('\n').map(line => `   ${line}`).join('\n');
    return `${++n}. On "${node}"${under}:\n${body}\n`;
  };
  const parts = [`Comments on ${file}:\n`, ...placed.map(item)];
  if (orphans.length) {
    parts.push(`These comments' nodes no longer match any node in ${file}, since a node's text or place changed ` +
               'after the comment:\n', ...orphans.map(item));
  }
  return parts.join('\n');
}
