"""The checks the design trees spec gives CI: what breaks a tree fails, and sizes warn until they're far off.
Standard library only."""
import os
from pathlib import Path

from tree_model import LINK, nodes, own_words, parse, where

# The spec's targets. A size past its target warns, and past 1.5 times it fails.
NODE_WORDS = 40
CHILDREN = 7
VIEW_WORDS = 150
FILE_WORDS = 1500
# A nested subtree this small, or a promoted file under MERGE_WORDS, only warns: it's a sign to flatten or merge back.
FLATTEN_WORDS = 60
MERGE_WORDS = 500


def tree_roots(repo):
    """Each tree's root file, `<id>.tree/<id>.md`, anywhere in the repo outside dot-folders."""
    roots = []
    for folder, dirs, _ in os.walk(repo):
        dirs[:] = sorted(d for d in dirs if not d.startswith('.'))
        for d in dirs:
            if d.endswith('.tree'):
                roots.append(Path(folder) / d / (d[:-len('.tree')] + '.md'))
    return roots


def check(repo):
    """Every problem in the repo's trees, as (file, level, message), with level 'fail' or 'warn'."""
    problems, trees = [], [parse(root) for root in tree_roots(repo)]
    problems += [(file, 'fail', message) for tree in trees for file, message in tree.problems]
    for tree in trees:
        folder, page = tree.file.parent, tree.file.with_suffix('.html')
        for file in sorted(f for f in folder.rglob('*') if f.is_file()):
            if file.suffix != '.md' and file != page:
                problems.append((file, 'fail', "a .tree folder holds only the tree's Markdown and its rendered page"))
            elif file.suffix == '.md' and file not in tree.files:
                problems.append((file, 'fail', 'no More: line reaches this file'))
    by_id = {}
    for node in sorted((n for tree in trees for n in nodes(tree) if n.id), key=lambda n: n.file):
        by_id.setdefault(node.id, []).append(node)
    for first, *others in by_id.values():
        for node in others:
            problems.append((node.file, 'fail', f'{{#{node.id}}} is also the ID of a node in '
                                                f'{first.file.relative_to(repo)}'))
    ids = set(by_id)
    for tree in trees:
        for node in nodes(tree):
            for slug in LINK.findall(node.text):
                if slug not in ids:
                    problems.append((node.file, 'fail', f"[[{slug}]] doesn't resolve, under \"{where(node)}\""))
    for tree in trees:
        for node in nodes(tree):
            problems += sized(node.file, 'node text is {} words', own_words(node), NODE_WORDS, where(node))
            problems += sized(node.file, 'has {} children', len(node.children), CHILDREN, where(node))
            view = own_words(node) + sum(own_words(child) for child in node.children)
            if node.children:
                problems += sized(node.file, 'view is {} words', view, VIEW_WORDS, where(node))
            size = subtree_words(node)
            if any(child.children for child in node.children) and size <= FLATTEN_WORDS:
                problems.append((node.file, 'warn', f'nested subtree is {size} words (flatten at {FLATTEN_WORDS} or '
                                                    f'fewer), under "{where(node)}"'))
        for file, size in file_words(tree).items():
            problems += sized(file, 'file is {} words', size, FILE_WORDS)
            if file != tree.file and size < MERGE_WORDS:
                problems.append((file, 'warn', f'promoted file is {size} words (merge it back under {MERGE_WORDS})'))
    return problems


def subtree_words(node):
    return own_words(node) + sum(subtree_words(child) for child in node.children)


def sized(file, what, size, target, under=None):
    """A warning when size passes its target, or a failure past 1.5 times it."""
    limit, where_ = target * 3 // 2, f', under "{under}"' if under else ''
    if size > limit:
        return [(file, 'fail', f'{what.format(size)} (limit {limit}){where_}')]
    if size > target:
        return [(file, 'warn', f'{what.format(size)} (target {target}){where_}')]
    return []


def file_words(tree):
    """Each file in a tree, with the words of the nodes it holds."""
    per_file = {}
    for node in nodes(tree):
        per_file[node.file] = per_file.get(node.file, 0) + own_words(node)
    return per_file


def stats(repo):
    """Lines giving each file's size, then each view's size, child count and subtree size, indented by depth."""
    lines = []
    for tree in (parse(root) for root in tree_roots(repo)):
        lines += [f'{file.relative_to(repo)}: {size} words' for file, size in file_words(tree).items()]
        for node in nodes(tree):
            if node.children:
                count = len(node.children)
                view = own_words(node) + sum(own_words(child) for child in node.children)
                lines.append(f'{"  " * (node.depth + 1)}{where(node)}: view {view}, {count} '
                             f'{"child" if count == 1 else "children"}, subtree {subtree_words(node)}')
    return lines


def links_to(repo, slug):
    """Each node that links to the ID, as (file, text), in path order. None when no node has the ID."""
    trees = [parse(root) for root in tree_roots(repo)]
    every = [node for tree in trees for node in nodes(tree)]
    if not any(node.id == slug for node in every):
        return None
    return sorted((node.file, node.text.strip()) for node in every if slug in LINK.findall(node.text))
