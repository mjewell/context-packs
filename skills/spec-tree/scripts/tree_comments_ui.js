// Comments on a spec tree page, for a person to leave on nodes and copy to an agent as Markdown. They're kept in this
// browser's localStorage under the tree's file, so they outlive a re-render of the page. Inlined after
// tree_comments.mjs, whose placeComments and asMarkdown it uses, in a module of its own so its names can't clash
// with the page's other script.

const main = document.querySelector('main');
const file = main.dataset.tree;
const storeKey = `spec-tree-comments:${file}`;
const load = () => JSON.parse(localStorage.getItem(storeKey) || '[]');
const save = comments => localStorage.setItem(storeKey, JSON.stringify(comments));

function el(tag, attrs = {}, ...children) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  e.append(...children);
  return e;
}

// Every node is an <li data-src>, and its row is the leaf <li> itself or the branch's <summary>.
const nodes = [...main.querySelectorAll('li[data-src]')];
const pathOf = li => {
  const path = [];
  for (let l = li; l; l = l.parentElement.closest('li[data-src]')) path.unshift(l.dataset.src);
  return path;
};
const paths = nodes.map(pathOf);
const noteRow = li => li.classList.contains('leaf') ? li : li.querySelector(':scope > details > summary');
const boxes = nodes.map(li => {
  const row = noteRow(li);
  const box = el('div', { class: 'notes' });
  row.append(el('button', { type: 'button', class: 'note-add', title: 'Comment on this node (c)' }, '+ Comment'), box);
  return box;
});

const copy = el('button', { type: 'button' });
const clear = el('button', { type: 'button', 'data-confirm': 'Delete every comment?' }, 'Delete all comments');
document.querySelector('.tools').append(copy, clear);
const orphanList = el('div');
const orphans = el('section', { class: 'orphans' },
  el('h2', {}, 'Comments on nodes that changed'),
  el('p', {}, "These nodes' text or place changed after the comment, so no node here matches them."),
  orphanList);
main.querySelector(':scope > ul').before(orphans);

function note(c, { withPath = false } = {}) {
  return el('div', { class: 'note' },
    el('div', { class: 'note-body' },
      ...(withPath ? [el('div', { class: 'note-path' }, c.path.join(' › '))] : []),
      el('p', { class: 'note-text' }, c.text)),
    el('button', { type: 'button', 'data-note-delete': c.id, 'data-confirm': 'Delete?' }, 'Delete'));
}

function render() {
  const placed = placeComments(load(), paths);
  boxes.forEach((box, i) => box.replaceChildren(...placed.byRow[i].map(c => note(c))));
  orphanList.replaceChildren(...placed.orphans.map(c => note(c, { withPath: true })));
  orphans.hidden = !placed.orphans.length;
  const count = placed.byRow.flat().length + placed.orphans.length;
  copy.textContent = `Copy comments for agent (${count})`;
  copy.disabled = clear.disabled = !count;
}

// The first click arms the button and the second, within 3 seconds, acts. This works in any browser, unlike
// confirm(), which a page shown inside an editor may block, and a blocked confirm() returns false with no error.
function confirmed(button) {
  if (button.dataset.armed) return true;
  const label = button.textContent;
  button.dataset.armed = '1';
  button.textContent = button.dataset.confirm;
  setTimeout(() => { delete button.dataset.armed; button.textContent = label; }, 3000);
  return false;
}

const editor = el('dialog', { class: 'note-editor' });
const target = el('p', { class: 'note-target' });
const input = el('textarea', { rows: '5', placeholder: 'Comment for the agent' });
const saveButton = el('button', { value: 'save' }, 'Save');
const form = el('form', { method: 'dialog' }, target, input, el('div', { class: 'note-actions' },
  el('span', { class: 'note-hint' }, '↩ to save, ⇧↩ for a new line, Esc to cancel'),
  el('button', { value: 'cancel' }, 'Cancel'),
  saveButton));
editor.append(form);
document.body.append(editor);
let editing = null;

function openEditor(li) {
  editing = li;
  target.textContent = `On "${li.dataset.src}"`;
  input.value = '';
  editor.returnValue = '';
  editor.showModal();
  input.focus();
}
editor.addEventListener('close', () => {
  const text = input.value.trim();
  if (editor.returnValue === 'save' && text) {
    const id = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
    save([...load(), { id, path: pathOf(editing), text }]);
    render();
  }
  noteRow(editing).focus();
});
// A click on the backdrop lands on the dialog itself, outside its box. It closes an empty editor, and leaves one
// with text open, so a stray click can't lose a comment.
editor.addEventListener('click', e => {
  const box = editor.getBoundingClientRect();
  const outside = e.clientX < box.left || e.clientX > box.right || e.clientY < box.top || e.clientY > box.bottom;
  if (e.target === editor && outside && !input.value.trim()) editor.close('cancel');
});
// Esc is handled here rather than left to the dialog, since VS Code's built-in browser doesn't close a dialog on Esc.
editor.addEventListener('keydown', e => {
  if (e.key === 'Escape') { e.preventDefault(); editor.close('cancel'); }
});
input.addEventListener('keydown', e => {
  // Enter saves and Shift+Enter adds a line, as in a chat box. An Enter that confirms an input method's composition
  // belongs to it. Submitted as the Save button would be, so both close the editor the same way.
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); form.requestSubmit(saveButton); }
});

document.addEventListener('keydown', e => {
  if (e.key !== 'c' || e.altKey || e.ctrlKey || e.metaKey || !document.activeElement.matches('.row')) return;
  e.preventDefault();
  openEditor(document.activeElement.closest('li'));
});

document.addEventListener('click', async e => {
  // A click on a comment, or on its buttons, sits inside a branch's <summary>, and mustn't open or close the branch.
  if (e.target.closest('.notes, .note-add')) e.preventDefault();
  const add = e.target.closest('.note-add');
  if (add) return openEditor(add.closest('li'));
  const del = e.target.closest('[data-note-delete]');
  if (del && confirmed(del)) {
    save(load().filter(c => c.id !== del.dataset.noteDelete));
    return render();
  }
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

render();
