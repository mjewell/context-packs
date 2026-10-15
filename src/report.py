"""What a sync changed, in lines for the person who ran it."""
from origins import COMMIT


def short(ref):
    """ref as git shows it: a commit abbreviated, a tag in full."""
    return ref[:7] if COMMIT.fullmatch(ref) else ref


def at(imported):
    """Where the import pack pins its pack, or nothing for a local one, which syncs from its working tree."""
    return f' @ {short(imported.ref)}' if imported.ref else ''


def changes(found, written, created, linked, before, after):
    """Lines describing what the sync did: whether it created AGENTS.md and linked CLAUDE.md to it, how the import
    packs before it became the ones after, and otherwise whether the block it found differs from the one it wrote."""
    was = {i.id: i for i in before}
    now = {i.id: i for i in after}
    lines = ['Created AGENTS.md'] * created + ['Linked CLAUDE.md to AGENTS.md'] * linked
    for id, imported in now.items():
        if id not in was:
            lines.append(f'{id}: added{at(imported)}')
        elif was[id].ref != imported.ref:
            lines.append(f'{id}: {short(was[id].ref)} → {short(imported.ref)}')
    lines += [f'{id}: removed' for id in was if id not in now]
    if not lines and found.block != written:
        lines.append('Updated the context-packs block')
    if lines:
        return lines
    pins = [i.id + at(i) for i in after]
    return [f'Nothing changed: {", ".join(pins)}' if pins else 'Nothing changed']
