"""A design tree read from its Markdown file: nodes with their text, ID, children and diagrams. Standard library
only."""
import re

LABELS = ('Why', 'Rejected')
ID = re.compile(r'\s*\{#([\w-]+)\}\s*$')
# Anything else in braces at the end of a node's text, such as `{#a #b}`, which the spec no longer allows.
BAD_ID = re.compile(r'\{#[^}]*\}\s*$')
LINK = re.compile(r'\[\[([\w-]+)\]\]')


class Node:
    def __init__(self, text, depth):
        self.text, self.depth, self.children, self.diagrams, self.id = text, depth, [], [], None
        m = ID.search(text)
        if m:
            self.id = m.group(1)
            self.text = text[:m.start()]


def parse(path):
    """The root (title, intro, id) and its top-level nodes. A fenced block belongs to the node above it. What stops a
    file reading as a tree is kept in the root's `problems`, as (file, message), and the rest of it is still read."""
    root = Node('', -1)
    root.title, root.intro, root.file, root.problems = path.name.removesuffix('.tree.md'), [], path, []
    stack, fence, lines = [root], None, path.read_text(encoding='utf-8').splitlines()
    for line in lines:
        stripped = line.strip()
        if fence is not None:
            if stripped.startswith('```'):
                stack[-1].diagrams.append(fence)
                fence = None
            else:
                fence['lines'].append(line)
            continue
        if stripped.startswith('```'):
            fence = {'lang': stripped[3:].strip(), 'lines': [], 'indent': len(line) - len(line.lstrip())}
            continue
        if not stripped or stripped.startswith('---') and stack == [root] and not root.children:
            continue
        if line.startswith('# '):
            head = Node(line[2:], -1)
            root.title, root.id = head.text, head.id
            continue
        m = re.match(r'^( *)- (.*)$', line)
        if not m:
            if not root.children:
                root.intro.append(stripped)
            continue
        depth = len(m.group(1)) // 2
        while stack[-1].depth >= depth:
            stack.pop()
        node = Node(m.group(2), depth)
        node.file = path
        if not node.id and BAD_ID.search(node.text):
            root.problems.append((path, f'a node has one ID, written {{#slug}}, under "{where(node)}"'))
        stack[-1].children.append(node)
        stack.append(node)
    for d in all_diagrams(root):
        d['source'] = '\n'.join(l[d['indent']:] for l in d['lines'])
    return root


def all_diagrams(node):
    yield from node.diagrams
    for child in node.children:
        yield from all_diagrams(child)


def label_of(text):
    for label in LABELS:
        if text.startswith(label + ':'):
            return label, text[len(label) + 1:].strip()
    return None, text


def collect_ids(node, out):
    if node.id:
        out.add(node.id)
    for child in node.children:
        collect_ids(child, out)
    return out


def nodes(node):
    """The node and every node below it, in reading order."""
    yield node
    for child in node.children:
        yield from nodes(child)


def where(node):
    """A node's text, short enough to name it in a message. The root is named by its title."""
    text = node.text.strip() or getattr(node, 'title', '')
    return text if len(text) <= 50 else text[:49] + '…'


def words(text):
    """Words in a node's text, as the spec counts them: labels, IDs, links and code spans don't count."""
    text = re.sub(r'^(Why|Rejected):', ' ', text.strip())
    text = re.sub(r'`[^`]*`', ' ', LINK.sub(' ', text))
    text = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', text)
    return len([w for w in re.sub(r'[*_]', ' ', text).split() if re.search(r'\w', w)])


def own_words(node):
    """Words in what a node shows: its text, or for the root, the sentence under its title."""
    return words(' '.join(node.intro)) if hasattr(node, 'intro') else words(node.text)
