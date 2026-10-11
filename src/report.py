"""What a sync changed, in lines for the person who ran it."""
from blocks import HEADER
from origins import COMMIT


def short(ref):
    """ref as git shows it: a commit abbreviated, a tag in full."""
    return ref[:7] if COMMIT.fullmatch(ref) else ref


def at(pack):
    """Where the pack is pinned, or nothing for one that syncs from the repo's working tree."""
    return f' @ {short(pack.ref)}' if pack.ref else ''


def sets(names):
    return ', '.join(names) or 'none'


def changes(found, after, chosen, blocks, created, linked):
    """Lines describing what the sync did: whether it created AGENTS.md or found CLAUDE.md already linked to it, and
    how the packs found in AGENTS.md became the packs after it, with chosen holding the doc sets each pack installs
    and blocks the text the sync wrote for each."""
    before = found.packs
    old = {p.name: p for p in before}
    new = {p.name for p in after}
    lines = (['Created AGENTS.md'] * created + ['Linked CLAUDE.md to AGENTS.md'] * (not linked)
             + ['Updated the header block'] * (not created and found.blocks[HEADER] != blocks[HEADER]))
    for pack in after:
        was = old.get(pack.name)
        if not was:
            docs = chosen[pack.name]
            lines.append(f'{pack.name}: added{at(pack)}' + f' (docs: {sets(docs)})' * bool(docs))
        elif was.ref != pack.ref:
            lines.append(f'{pack.name}: {short(was.ref)} → {short(pack.ref)}')
        elif was.docs != pack.docs:
            lines.append(f'{pack.name}: doc sets {sets(was.docs)} → {sets(pack.docs)}')
        elif found.blocks[pack.name] != blocks[pack.name]:
            lines.append(f'{pack.name}: changed')
    lines += [f'{p.name}: removed' for p in before if p.name not in new]
    if lines:
        return lines
    return [f'Nothing changed: {", ".join(p.name + at(p) for p in after) or "no packs installed"}']
