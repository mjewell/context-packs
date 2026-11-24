// Comments on a spec tree page, for a person to leave on nodes and copy to an agent as Markdown. They're kept in this
// browser's localStorage under the tree's file, so they outlive a re-render of the page. Inlined after
// tree_comments.mjs, whose placeComments and asMarkdown it uses, in a module of its own so its names can't clash
// with the page's other script.

const main = document.querySelector('main');
const file = main.dataset.tree;
const storeKey = `spec-tree-comments:${file}`;
const load = () => JSON.parse(localStorage.getItem(storeKey) || '[]');
const save = (comments) => localStorage.setItem(storeKey, JSON.stringify(comments));

function el(tag, attrs = {}, ...children) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  e.append(...children);
  return e;
}

// Every node is an <li data-src>, and its row is the leaf <li> itself or the branch's <summary>. A comment is anchored
// on data-src, the node's source text, and a person reads data-text, the text as the page shows it.
const nodes = [...main.querySelectorAll('li[data-src]')];
const pathOf = (li) => {
  const path = [];
  for (let l = li; l; l = l.parentElement.closest('li[data-src]')) path.unshift(l.dataset.src);
  return path;
};
const paths = nodes.map(pathOf);
const noteRow = (li) => (li.classList.contains('leaf') ? li : li.querySelector(':scope > details > summary'));
// A node holds one comment. Its button, and c on its row, start the comment or open the one it has. Comments stored
// before that rule can still put two on a node, and both show until the person deletes one.
const addButtons = nodes.map(() =>
  el('button', { type: 'button', class: 'note-add', title: 'Comment on this node (c)' }),
);
const boxes = nodes.map((li, i) => {
  const box = el('div', { class: 'notes' });
  noteRow(li).append(addButtons[i], box);
  return box;
});
const commentOn = (li) => placeComments(load(), paths).byRow[nodes.indexOf(li)][0] || null;
// A branch's marker counts the comments on the nodes below it. It shows only while the branch is collapsed, since
// an open branch shows those comments' rows.
const markers = nodes.map((li) => {
  if (li.classList.contains('leaf')) return null;
  const marker = el('span', { class: 'note-count', title: 'Comments on the nodes below' });
  noteRow(li).querySelector('.note-add').before(marker);
  return marker;
});

// The sidebar floats at the right. On a wide window the open sidebar pushes the tree aside, and on a narrow one it
// covers part of it. It starts open only on a wide window, and then keeps whatever its toggle last chose. The width
// matches the CSS's @media rule that moves the tree aside.
const wide = matchMedia('(min-width: 1200px)');
const panelKey = 'spec-tree-comments-panel';
const toggle = el('button', { type: 'button', class: 'panel-toggle', 'aria-expanded': 'false' });
const copy = el('button', { type: 'button' });
const clear = el('button', { type: 'button', 'data-confirm': 'Delete every comment?' }, 'Delete all');
const index = el('ol', { class: 'note-index' });
const empty = el(
  'p',
  { class: 'panel-empty' },
  'No comments yet. Hover a row and click "+ Comment", or press c on a focused row.',
);
const orphanList = el('div');
const orphans = el(
  'section',
  { class: 'orphans' },
  el('h2', {}, 'On nodes that changed'),
  el('p', {}, "These nodes' text or place changed after the comment, so no node here matches them."),
  orphanList,
);
const panel = el(
  'aside',
  { class: 'notes-panel' },
  toggle,
  el('div', { class: 'panel-body' }, el('div', { class: 'panel-actions' }, copy, clear), empty, index, orphans),
);
document.body.append(panel);
function setPanel(open) {
  panel.classList.toggle('open', open);
  document.body.classList.toggle('panel-open', open);
  toggle.setAttribute('aria-expanded', String(open));
}
const remembered = localStorage.getItem(panelKey);
setPanel(remembered ? remembered === 'open' : wide.matches);
// Where the open sidebar covers the tree, a click on the page collapses it, and still does what it landed on. It
// isn't remembered, so a collapse on a narrow window doesn't make a wide one start collapsed.
document.addEventListener('click', (e) => {
  if (panel.classList.contains('open') && !wide.matches && !panel.contains(e.target)) setPanel(false);
});

// A comment opens the editor when clicked, to edit or delete it. It takes no keyboard focus, since c on its node's
// row opens the same editor.
function note(c, { withPath = false } = {}) {
  return el(
    'div',
    { class: 'note', 'data-note': c.id, title: 'Edit or delete' },
    ...(withPath ? [el('div', { class: 'note-path' }, c.path.join(' › '))] : []),
    el('p', { class: 'note-text' }, c.text),
  );
}

function render() {
  const placed = placeComments(load(), paths);
  for (const [i, box] of boxes.entries()) box.replaceChildren(...placed.byRow[i].map((c) => note(c)));
  addButtons.forEach((button, i) => {
    button.textContent = placed.byRow[i].length ? 'Edit comment' : '+ Comment';
  });
  markers.forEach((marker, i) => {
    if (!marker) return;
    const below = nodes[i].querySelectorAll(':scope > details > ul .note').length;
    marker.textContent = `💬 ${below}`;
    marker.hidden = !below;
  });
  index.replaceChildren(
    ...placed.byRow.flatMap((comments, i) =>
      comments.map((c) =>
        el(
          'li',
          {},
          el(
            'button',
            { type: 'button', class: 'index-entry', 'data-row': String(i) },
            el('span', { class: 'index-node' }, nodes[i].dataset.text),
            el('span', { class: 'index-text' }, c.text),
          ),
        ),
      ),
    ),
  );
  orphanList.replaceChildren(...placed.orphans.map((c) => note(c, { withPath: true })));
  orphans.hidden = !placed.orphans.length;
  const count = placed.byRow.flat().length + placed.orphans.length;
  empty.hidden = !!count;
  toggle.textContent = `💬 Comments (${count})`;
  copy.textContent = 'Copy for agent';
  copy.disabled = clear.disabled = !count;
}

// Opens the branches above a node and focuses its row, as a [[link]] jump does in the page's other script.
function showNode(li) {
  for (let d = li.parentElement.closest('details'); d; d = d.parentElement.closest('details')) d.open = true;
  const row = noteRow(li);
  row.focus({ preventScroll: true });
  row.scrollIntoView({ block: 'center' });
  li.classList.add('flash');
  setTimeout(() => li.classList.remove('flash'), 1200);
}

// The first click arms the button and the second, within 3 seconds, acts. This works in any browser, unlike
// confirm(), which a page shown inside an editor may block, and a blocked confirm() returns false with no error. A
// button that stays on the page across uses, such as the editor's Delete, calls disarm() each time it's shown again,
// or it would still be armed from its last use and act on one click.
const disarms = new Map();
function confirmed(button) {
  if (button.dataset.armed) return true;
  const label = button.textContent;
  button.dataset.armed = '1';
  button.textContent = button.dataset.confirm;
  const reset = () => {
    clearTimeout(timer);
    disarms.delete(button);
    delete button.dataset.armed;
    button.textContent = label;
  };
  disarms.set(button, reset);
  const timer = setTimeout(reset, 3000);
  return false;
}
const disarm = (button) => disarms.get(button)?.();

const editor = el('dialog', { class: 'note-editor' });
const target = el('p', { class: 'note-target' });
const input = el('textarea', { rows: '5', placeholder: 'Comment for the agent' });
const saveButton = el('button', { value: 'save' }, 'Save');
const deleteButton = el('button', { type: 'button', 'data-confirm': 'Delete?' }, 'Delete');
const form = el(
  'form',
  { method: 'dialog' },
  target,
  input,
  el(
    'div',
    { class: 'note-actions' },
    deleteButton,
    el('span', { class: 'note-hint' }, '↩ to save, ⇧↩ for a new line, Esc to cancel'),
    el('button', { value: 'cancel' }, 'Cancel'),
    saveButton,
  ),
);
editor.append(form);
document.body.append(editor);
// What the open editor works on: the node's <li>, or null for an orphan, and the comment, or null for a new one.
let editing = null;

// Save stays disabled while the text is empty, so a comment is only ever removed through Delete.
const syncSave = () => {
  saveButton.disabled = !input.value.trim();
};
input.addEventListener('input', syncSave);

function openEditor(li, comment = null) {
  editing = { li, comment };
  // An orphan's node is gone, so it's named by the source text it was left on.
  target.textContent = `On "${li ? li.dataset.text : comment.path[comment.path.length - 1]}"`;
  input.value = comment ? comment.text : '';
  deleteButton.hidden = !comment;
  disarm(deleteButton);
  syncSave();
  editor.returnValue = '';
  editor.showModal();
  input.focus();
}
editor.addEventListener('close', () => {
  const { li, comment } = editing;
  const text = input.value.trim();
  if (editor.returnValue === 'save' && comment) {
    // Another tab can delete the comment while this editor has it open. The save is the later write, so it puts the
    // comment back, as the later of two edits from two tabs wins.
    const stored = load();
    save(
      stored.some((c) => c.id === comment.id)
        ? stored.map((c) => (c.id === comment.id ? { ...c, text } : c))
        : [...stored, { ...comment, text }],
    );
  } else if (editor.returnValue === 'save') {
    const id = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
    save([...load(), { id, path: pathOf(li), text }]);
  } else if (editor.returnValue === 'delete') {
    save(load().filter((c) => c.id !== comment.id));
  }
  render();
  if (li) noteRow(li).focus();
});
deleteButton.addEventListener('click', () => {
  if (confirmed(deleteButton)) editor.close('delete');
});
// A click on the backdrop lands on the dialog itself, outside its box. It closes an empty editor, and leaves one
// with text open, so a stray click can't lose a comment.
editor.addEventListener('click', (e) => {
  const box = editor.getBoundingClientRect();
  const outside = e.clientX < box.left || e.clientX > box.right || e.clientY < box.top || e.clientY > box.bottom;
  if (e.target === editor && outside && !input.value.trim()) editor.close('cancel');
});
// Esc is handled here rather than left to the dialog, since VS Code's built-in browser doesn't close a dialog on Esc.
editor.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    e.preventDefault();
    editor.close('cancel');
  }
});
input.addEventListener('keydown', (e) => {
  // Enter saves and Shift+Enter adds a line, as in a chat box. An Enter that confirms an input method's composition
  // belongs to it. Submitted as the Save button would be, so both close the editor the same way.
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    if (!saveButton.disabled) form.requestSubmit(saveButton);
  }
});

// Opens the editor on the comment a note shows. An orphan's note sits in the sidebar, under no node's <li>.
function editNote(noteEl) {
  const comment = load().find((c) => c.id === noteEl.dataset.note);
  // Another tab can delete it in the moment before the storage event re-renders this one. Opened anyway, the editor
  // would save the text as a new comment.
  if (!comment) throw new Error(`comment ${noteEl.dataset.note} is no longer stored; reload the page`);
  openEditor(noteEl.closest('li[data-src]'), comment);
}

document.addEventListener('keydown', (e) => {
  if (e.key !== 'c' || e.altKey || e.ctrlKey || e.metaKey || !document.activeElement.matches('.row')) return;
  e.preventDefault();
  const li = document.activeElement.closest('li');
  openEditor(li, commentOn(li));
});

document.addEventListener('click', async (e) => {
  // A click on a comment, or on the button that adds one, sits inside a branch's <summary>, and mustn't open or close
  // the branch.
  if (e.target.closest('.notes, .note-add')) e.preventDefault();
  if (e.target === toggle) {
    const open = !panel.classList.contains('open');
    localStorage.setItem(panelKey, open ? 'open' : 'closed');
    return setPanel(open);
  }
  const entry = e.target.closest('.index-entry');
  if (entry) return showNode(nodes[Number(entry.dataset.row)]);
  const add = e.target.closest('.note-add');
  if (add) return openEditor(add.closest('li'), commentOn(add.closest('li')));
  const noteEl = e.target.closest('.note');
  if (noteEl) return editNote(noteEl);
  if (e.target === clear && confirmed(clear)) {
    localStorage.removeItem(storeKey);
    return render();
  }
  if (e.target === copy) {
    const placed = placeComments(load(), paths);
    try {
      await navigator.clipboard.writeText(asMarkdown(file, placed.byRow.flat(), placed.orphans));
      copy.textContent = 'Copied';
    } catch (err) {
      console.error('copying comments', err);
      copy.textContent = 'Copy failed, see the console';
    }
    setTimeout(render, 1500);
  }
});

// A change another tab of this page makes to the comments reaches this one as a storage event, so the page shows
// what's stored rather than a comment that tab deleted. A tab doesn't get the event for its own writes.
addEventListener('storage', (e) => {
  if (e.key === storeKey) render();
});

render();
