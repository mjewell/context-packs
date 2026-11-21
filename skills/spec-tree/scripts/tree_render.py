"""A parsed spec tree as one HTML page, with every level below the top collapsed. `[[slug]]` links jump to the
node with that ID and open its ancestors. Mermaid blocks render in the browser when their node is opened. D2 blocks
render to SVG here, through the `d2` CLI, which must be installed when a tree has one. Standard library only."""
import html
import json
import re
import shutil
import subprocess
import sys

from tree_model import collect_ids, label_of, nodes

MERMAID = 'https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.esm.min.mjs'
# ELK lays out nested containers more tidily than D2's default, and its spacing is tightened so a diagram stays
# small. Theme 200 is D2's dark theme, which the SVG switches to through prefers-color-scheme.
D2_ARGS = ['--layout', 'elk', '--elk-nodeNodeBetweenLayers', '30', '--elk-edgeNodeBetweenLayers', '15',
           '--elk-padding', '[top=20,left=12,bottom=12,right=12]', '--theme', '0', '--dark-theme', '200', '--pad', '4',
           '-', '-']
# Smaller text than D2's 16px default, set here so a tree's diagrams don't each repeat it.
D2_STYLE = '**.style.font-size: 13\n(** -> **)[*].style.font-size: 12\n'
SCHEME = re.compile(r'[a-z][a-z0-9+.-]*:', re.IGNORECASE)
SAFE_SCHEMES = {'http:', 'https:', 'mailto:'}


def inline(text, ids):
    """Escape, then render code spans, bold, Markdown links, and [[slug]] and [[slug|text]] links."""
    out, parts = [], re.split(r'(`[^`]*`)', text)
    for part in parts:
        if part.startswith('`') and part.endswith('`') and len(part) > 1:
            out.append(f'<code>{html.escape(part[1:-1])}</code>')
            continue
        # Quotes too, since a link's URL lands in an href.
        part = html.escape(part)
        part = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', part)
        part = re.sub(r'\[([^\]]+)\]\(([^)\s]+)\)', lambda m: f'<a href="{href(m.group(2))}">{m.group(1)}</a>', part)
        part = re.sub(r'\[\[([\w-]+)(?:\|([^\]|]+))?\]\]', lambda m: link(m.group(1), m.group(2) or m.group(1), ids),
                      part)
        out.append(part)
    return ''.join(out)


def href(url):
    """A Markdown link's URL, already escaped, once `check_link` allows it."""
    check_link(html.unescape(url), 'a link')
    return url


def check_link(url, what):
    """Stops the render on a link the page mustn't hold. A tree can come from anyone who sends a PR, so a scheme that
    can run script, such as javascript:, stops it rather than reaching the page. So does a control character, since
    browsers drop one at the start of a URL and read the scheme after it."""
    scheme = SCHEME.match(url)
    if not url.isprintable() or (scheme and scheme.group().lower() not in SAFE_SCHEMES):
        sys.exit(f'trees.py: {what} goes to {url!r}, and a page links only to relative, http(s): and mailto: URLs.')


def link(slug, text, ids):
    """A jump to the node with the ID, showing text, which is already escaped."""
    if slug in ids:
        return f'<a class="jump" href="#{slug}">{text}</a>'
    return f'<span class="jump missing" title="Not in this tree">{text}</span>'



def render_text(node, ids):
    label, rest = label_of(node.text.strip())
    body = inline(rest, ids)
    badge = f'<span class="label label-{label.lower()}">{label}</span>' if label else ''
    anchors = f'<a class="anchor" href="#{node.id}" title="Link to #{node.id}">#</a>' if node.id else ''
    return f'{badge}<span class="text">{body}</span>{anchors}'


def render_diagrams(node):
    out = []
    for d in node.diagrams:
        if d['lang'] == 'mermaid':
            out.append(f'<pre class="mermaid" data-pending="1">{html.escape(d["source"])}</pre>')
        elif d['lang'] == 'd2':
            out.append(f'<div class="d2">{d2_svg(d["source"], node)}</div>')
        else:
            out.append(f'<pre class="block"><code>{html.escape(d["source"])}</code></pre>')
    return ''.join(out)


def d2_svg(source, node):
    if not shutil.which('d2'):
        sys.exit('trees.py: this tree has a D2 diagram, and the d2 CLI is not installed. See https://d2lang.com.')
    result = subprocess.run(['d2', *D2_ARGS], input=D2_STYLE + source, capture_output=True, text=True)
    if result.returncode != 0:
        where = node.text.strip()[:60] or 'the root'
        sys.exit(f'trees.py: the D2 diagram under "{where}" failed:\n{result.stderr.strip()}')
    # Inline, so the SVG keeps D2's links and selectable text. So every href in it, which d2 writes as both href and
    # xlink:href, is held to the rule a Markdown link follows.
    for _, value in re.findall(r'\bhref\s*=\s*(["\'])(.*?)\1', result.stdout):
        check_link(html.unescape(value), f'a link in the D2 diagram under "{node.text.strip()[:60] or "the root"}"')
    return re.sub(r'^<\?xml[^>]*\?>', '', result.stdout)


def render_node(node, ids):
    id_attr = f' id="{node.id}"' if node.id else ''
    text = render_text(node, ids)
    if not node.children and not node.diagrams:
        return f'<li class="leaf row" tabindex="-1"{id_attr}>{text}</li>'
    # Every node below, not just the children: the size rules keep a node's children to about 7, so that count would
    # barely vary, and the children show as soon as the branch opens.
    below = sum(1 for _ in nodes(node)) - 1
    title = f'{below} node{"" if below == 1 else "s"} below'
    meta = f'<span class="count" title="{title}">{below}</span>' if below else ''
    kids = ''.join(render_node(c, ids) for c in node.children)
    return (f'<li class="branch"{id_attr}><details><summary class="row" tabindex="-1">{text}{meta}</summary>'
            f'{render_diagrams(node)}<ul>{kids}</ul></details></li>')


def page(root):
    ids = collect_ids(root, set())
    title = html.escape(root.title)
    intro = inline(' '.join(root.intro), ids)
    tree = ''.join(render_node(c, ids) for c in root.children)
    return TEMPLATE.format(title=title, intro=intro, root_diagrams=render_diagrams(root), tree=tree,
                           script=SCRIPT.replace('__MERMAID__', json.dumps(MERMAID)))


TEMPLATE = '''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
:root {{ --bg:#fbfaf8; --fg:#1d1d1f; --muted:#6b6b70; --line:#e2e0db; --accent:#3b5bdb; --why:#2b8a3e;
  --rejected:#c92a2a; --hl:#fff3bf; --chip:#f1efea; --focus:#e5eaff;
  --chevron:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Cpath d='M6 4l4 4-4 4' fill='none' stroke='black' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E"); }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#17171a; --fg:#e8e6e3; --muted:#9a9aa0; --line:#2e2e33;
  --accent:#91a7ff; --why:#69db7c; --rejected:#ff8787; --hl:#4a3f12; --chip:#26262b;
  --focus:#283052; }} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--fg); font:16px/1.55 ui-sans-serif, system-ui, -apple-system, sans-serif; }}
main {{ max-width:860px; margin:0 auto; padding:40px 16px 80px; }}
h1 {{ font-size:28px; margin:0 0 6px; letter-spacing:-0.01em; }}
.intro {{ color:var(--muted); margin:0 0 20px; font-size:17px; }}
.tools {{ display:flex; gap:8px; margin-bottom:18px; }}
button {{ font:inherit; font-size:13px; padding:4px 10px; border:1px solid var(--line); border-radius:6px;
  background:var(--chip); color:var(--fg); cursor:pointer; }}
ul {{ list-style:none; margin:0; padding:0 0 0 22px; border-left:1px solid var(--line); }}
main > ul {{ padding-left:0; border-left:none; }}
li {{ margin:2px 0; }}
li.leaf {{ padding:3px 0 3px 24px; position:relative; }}
li.leaf::before {{ content:""; position:absolute; left:6px; top:14px; width:4px; height:4px; border-radius:50%;
  background:var(--muted); opacity:.6; }}
summary {{ cursor:pointer; padding:3px 0; list-style:none; display:block; position:relative; padding-left:24px; }}
summary::-webkit-details-marker {{ display:none; }}
summary::before, summary::after {{ content:""; position:absolute; left:0; top:7px; width:16px; height:16px;
  box-sizing:border-box; }}
summary::before {{ border-radius:4px; background:var(--chip); border:1px solid var(--line); }}
summary::after {{ background:var(--fg); -webkit-mask:var(--chevron) center/contain no-repeat; mask:var(--chevron) center/contain no-repeat;
  transition:transform .12s; }}
details[open] > summary::after {{ transform:rotate(90deg); }}
summary:hover::before {{ border-color:var(--accent); }}
summary:hover .text {{ color:var(--accent); }}
.count {{ margin-left:8px; font-size:12px; color:var(--muted); background:var(--chip); border-radius:10px; padding:0 7px; }}
.label {{ font-size:11px; font-weight:600; text-transform:uppercase; letter-spacing:.04em; margin-right:7px;
  padding:1px 6px; border-radius:4px; vertical-align:1px; }}
.label-why {{ color:var(--why); border:1px solid currentColor; }}
.label-rejected {{ color:var(--rejected); border:1px solid currentColor; }}
code {{ font:13px ui-monospace, SFMono-Regular, Menlo, monospace; background:var(--chip); padding:1px 4px; border-radius:4px; }}
a {{ color:var(--accent); }}
.anchor {{ margin-left:6px; color:var(--muted); text-decoration:none; opacity:0; font-size:13px; }}
li:hover > .anchor, summary:hover .anchor, li.leaf:hover .anchor {{ opacity:1; }}
/* A tree links each use of a term, so a jump stays quiet until it's pointed at. */
a.jump {{ color:inherit; text-decoration:underline dotted var(--muted); text-underline-offset:3px; }}
a.jump:hover {{ color:var(--accent); text-decoration-color:var(--accent); }}
.jump.missing {{ color:var(--muted); border-bottom:1px dashed var(--muted); }}
.flash > details > summary, li.leaf.flash {{ background:var(--hl); border-radius:4px; }}
pre {{ margin:6px 0 10px 24px; overflow-x:auto; }}
pre.mermaid {{ background:transparent; }}
pre.block {{ background:var(--chip); padding:10px; border-radius:6px; }}
.d2 {{ margin:6px 0 12px 24px; overflow-x:auto; }}
.d2 > svg {{ max-width:100%; max-height:360px; width:auto; height:auto; display:block; }}
.row:focus {{ outline:none; background:var(--focus); border-radius:4px; }}
</style></head>
<body><main>
<h1>{title}</h1>
<p class="intro">{intro}</p>
{root_diagrams}
<div class="tools"><button data-act="open">Expand all</button><button data-act="close">Collapse all</button></div>
<ul>{tree}</ul>
</main>
<script type="module">{script}</script>
</body></html>
'''

# Not run through str.format, so its braces are written once. __MERMAID__ is replaced with the module's URL.
SCRIPT = '''
let mermaid = null;
async function draw(scope) {
  const pending = [...scope.querySelectorAll(':scope > pre.mermaid[data-pending]')];
  if (!pending.length) return;
  try {
    mermaid = mermaid || (await import(__MERMAID__)).default;
    const dark = matchMedia('(prefers-color-scheme: dark)').matches;
    mermaid.initialize({ startOnLoad: false, theme: dark ? 'dark' : 'neutral' });
    pending.forEach(p => p.removeAttribute('data-pending'));
    await mermaid.run({ nodes: pending });
  } catch (e) { console.error('mermaid', e); }
}
document.querySelectorAll('details').forEach(d => d.addEventListener('toggle', () => d.open && draw(d)));
draw(document.querySelector('main'));

// Rows are each branch's <summary> and each leaf <li>. One row at a time has tabindex 0 (a roving tabindex).
const isBranch = row => row.tagName === 'SUMMARY';
const detailsOf = row => row.parentElement;
const rowOf = li => li.classList.contains('leaf') ? li : li.querySelector(':scope > details > summary');
const parentRow = row => {
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
document.addEventListener('focusin', e => {
  const row = e.target.closest('.row');
  if (row && row !== current) focusRow(row);
});

function open(id) {
  const el = document.getElementById(id);
  if (!el) return null;
  const opened = [];
  for (let d = el.parentElement.closest('details'); d; d = d.parentElement.closest('details')) {
    if (!d.open) { d.open = true; opened.push(d); }
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
  opened.forEach(d => { d.open = false; });
  focusRow(row, { keepBack: true });
  row.scrollIntoView({ block: 'center' });
}
const linkIn = row => row.querySelector('.text a.jump');

document.addEventListener('keydown', e => {
  if (e.altKey || e.ctrlKey || e.metaKey) return;
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
    if (isBranch(row) && !detailsOf(row).open) { back.length = 0; detailsOf(row).open = true; return; }
    const link = linkIn(row);
    if (link) return jump(link.getAttribute('href').slice(1), row);
    const next = visible[i + 1];
    if (next && parentRow(next) === row) focusRow(next);
    return;
  }
  if (back.length) return goBack();
  if (isBranch(row) && detailsOf(row).open) { detailsOf(row).open = false; return; }
  focusRow(parentRow(row));
});

document.addEventListener('click', e => {
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
  if (b) document.querySelectorAll('details').forEach(d => { d.open = b.dataset.act === 'open'; });
});

const first = location.hash && open(location.hash.slice(1));
if (first) { focusRow(first.row); first.row.scrollIntoView({ block: 'center' }); flash(first.row); }
else { current = document.querySelector('.row'); if (current) current.tabIndex = 0; }
'''
