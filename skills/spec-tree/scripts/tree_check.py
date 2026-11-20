"""The checks ../spec.md gives CI: what breaks a tree fails, and sizes warn until they're far off.
Standard library only."""
import os
from pathlib import Path

from tree_model import LINK, nodes, own_words, parse, where

# The spec's targets. A size past its target warns, and past 1.5 times it fails.
NODE_WORDS = 40
CHILDREN = 7
VIEW_WORDS = 150
# A nested subtree this small only warns: it's a sign to flatten it.
FLATTEN_WORDS = 60


def tree_roots(repo):
    """Each tree's file, `<id>.tree.md`, anywhere in the repo outside dot-folders."""
    roots = []
    for folder, dirs, files in os.walk(repo):
        dirs[:] = sorted(d for d in dirs if not d.startswith('.'))
        roots += [Path(folder) / f for f in sorted(files) if f.endswith('.tree.md')]
    return roots


def check(repo):
    """Every problem in the repo's trees, as (file, level, message), with level 'fail' or 'warn'."""
    problems, trees = [], [parse(root) for root in tree_roots(repo)]
    problems += [(file, 'fail', message) for tree in trees for file, message in tree.problems]
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


def stats(repo):
    """Lines giving each view's size, child count and subtree size, indented by depth."""
    lines = []
    for tree in (parse(root) for root in tree_roots(repo)):
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
