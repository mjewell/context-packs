let mermaid = null;
async function draw(scope) {
  const pending = [...scope.querySelectorAll(':scope > pre.mermaid[data-pending]')];
  if (!pending.length) return;
  try {
    mermaid = mermaid || (await import(__MERMAID__)).default;
    const dark = matchMedia('(prefers-color-scheme: dark)').matches;
    mermaid.initialize({ startOnLoad: false, theme: dark ? 'dark' : 'neutral' });
    pending.forEach((p) => p.removeAttribute('data-pending'));
    await mermaid.run({ nodes: pending });
  } catch (e) {
    console.error('mermaid', e);
  }
}
document.querySelectorAll('details').forEach((d) => d.addEventListener('toggle', () => d.open && draw(d)));
draw(document.querySelector('main'));

// Rows are each branch's <summary> and each leaf <li>. One row at a time has tabindex 0 (a roving tabindex).
const isBranch = (row) => row.tagName === 'SUMMARY';
const detailsOf = (row) => row.parentElement;
const rowOf = (li) => (li.classList.contains('leaf') ? li : li.querySelector(':scope > details > summary'));
const parentRow = (row) => {
  const li = isBranch(row) ? detailsOf(row).parentElement : row;
  const d = li.parentElement.closest('details');
  return d ? d.querySelector(':scope > summary') : null;
};
function shown(row) {
  for (let r = parentRow(row); r; r = parentRow(r)) if (!detailsOf(r).open) return false;
  return true;
}
const rows = () => [...document.querySelectorAll('.row')].filter(shown);

// Each jump pushes where it came from and the branches it opened. Any other move clears the stack, so ← goes back
// only straight after a jump, or after a run of jumps.
const back = [];
let current = null;
function focusRow(row, { keepBack = false } = {}) {
  if (!row) return;
  if (!keepBack) back.length = 0;
  if (current) current.tabIndex = -1;
  current = row;
  row.tabIndex = 0;
  row.focus({ preventScroll: true });
  row.scrollIntoView({ block: 'nearest' });
}
document.addEventListener('focusin', (e) => {
  const row = e.target.closest('.row');
  if (row && row !== current) focusRow(row);
});

function open(id) {
  const el = document.getElementById(id);
  if (!el) return null;
  const opened = [];
  for (let d = el.parentElement.closest('details'); d; d = d.parentElement.closest('details')) {
    if (!d.open) {
      d.open = true;
      opened.push(d);
    }
  }
  return { row: rowOf(el.closest('li')), opened };
}
function flash(row) {
  const li = row.closest('li');
  li.classList.add('flash');
  setTimeout(() => li.classList.remove('flash'), 1200);
}
function jump(id, from) {
  const target = open(id);
  if (!target) return;
  back.push({ row: from, opened: target.opened });
  history.replaceState(null, '', '#' + id);
  focusRow(target.row, { keepBack: true });
  target.row.scrollIntoView({ block: 'center' });
  flash(target.row);
}
function goBack() {
  const { row, opened } = back.pop();
  opened.forEach((d) => {
    d.open = false;
  });
  focusRow(row, { keepBack: true });
  row.scrollIntoView({ block: 'center' });
}
// Links are followed with Tab and Enter, as on any page. → used to follow a row's first link, which made it jump
// on most rows once a tree linked every term.

document.addEventListener('keydown', (e) => {
  if (e.altKey || e.ctrlKey || e.metaKey) return;
  // Keys typed into a text field, such as a comment's, move its cursor instead.
  if (e.target.matches('textarea, input')) return;
  const keys = ['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Home', 'End'];
  if (!keys.includes(e.key)) return;
  e.preventDefault();
  const visible = rows();
  let row = current;
  while (row && !shown(row)) row = parentRow(row);
  if (!row || document.activeElement !== current) return focusRow(row || visible[0]);
  const i = visible.indexOf(row);
  if (e.key === 'ArrowDown') return focusRow(visible[i + 1]);
  if (e.key === 'ArrowUp') return focusRow(visible[i - 1]);
  if (e.key === 'Home') return focusRow(visible[0]);
  if (e.key === 'End') return focusRow(visible[visible.length - 1]);
  if (e.key === 'ArrowRight') {
    if (isBranch(row) && !detailsOf(row).open) {
      back.length = 0;
      detailsOf(row).open = true;
      return;
    }
    const next = visible[i + 1];
    if (next && parentRow(next) === row) focusRow(next);
    return;
  }
  if (back.length) return goBack();
  if (isBranch(row) && detailsOf(row).open) {
    detailsOf(row).open = false;
    return;
  }
  focusRow(parentRow(row));
});

document.addEventListener('click', (e) => {
  const a = e.target.closest('a.jump, a.anchor');
  if (a) {
    e.preventDefault();
    const id = a.getAttribute('href').slice(1);
    const from = a.closest('.row') || current;
    if (a.classList.contains('jump')) return jump(id, from);
    history.replaceState(null, '', '#' + id);
    return focusRow(from);
  }
  const b = e.target.closest('button[data-act]');
  if (b)
    document.querySelectorAll('details').forEach((d) => {
      d.open = b.dataset.act === 'open';
    });
});

const first = location.hash && open(location.hash.slice(1));
if (first) {
  focusRow(first.row);
  first.row.scrollIntoView({ block: 'center' });
  flash(first.row);
} else {
  current = document.querySelector('.row');
  if (current) current.tabIndex = 0;
}
