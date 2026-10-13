"""What a sync changed, in lines for the person who ran it."""
from blocks import HEADER
from origins import COMMIT


def short(ref):
    """ref as git shows it: a commit abbreviated, a tag in full."""
    return ref[:7] if COMMIT.fullmatch(ref) else ref


def at(pack):
    """Where the pack is pinned, or nothing for a local one, which syncs from its working tree."""
    return f' @ {short(pack.ref)}' if pack.ref else ''


def changes(found, after, blocks, created, linked, imported_before=(), imported_after=()):
    """Lines describing what the sync did: whether it created AGENTS.md and linked CLAUDE.md to it, how the packs
    found in the instructions file became the packs after it, with blocks the text the sync wrote for each, and how
    the import packs found became the ones after it. A marker naming an import pack is reported with its pin."""
    before = found.packs
    old = {p.name: p for p in before}
    new = {p.name for p in after}
    pinned_before = {i.holder: i.pack for i in imported_before if not i.id}
    pinned = {i.holder: i.pack for i in imported_after if not i.id}
    lines = (['Created AGENTS.md'] * created + ['Linked CLAUDE.md to AGENTS.md'] * linked
             + ['Updated the header block'] * (not created and found.blocks[HEADER] != blocks[HEADER]))
    for pack in after:
        pin, was_pin = pinned.get(pack.name, pack), pinned_before.get(pack.name, pack)
        if pack.name not in old:
            lines.append(f'{pack.name}: added{at(pin)}')
        elif was_pin.ref != pin.ref:
            lines.append(f'{pack.name}: {short(was_pin.ref)} → {short(pin.ref)}')
        elif found.blocks[pack.name] != blocks[pack.name]:
            lines.append(f'{pack.name}: changed')
    lines += [f'{p.name}: removed' for p in before if p.name not in new]
    was = {i.pack.name: i.pack for i in imported_before if i.id}
    now = {i.pack.name for i in imported_after if i.id}
    for pack in (i.pack for i in imported_after if i.id):
        if pack.name not in was:
            lines.append(f'{pack.name}: added{at(pack)}')
        elif was[pack.name].ref != pack.ref:
            lines.append(f'{pack.name}: {short(was[pack.name].ref)} → {short(pack.ref)}')
    lines += [f'{name}: removed' for name in was if name not in now]
    if lines:
        return lines
    pins = [pinned.get(p.name, p) for p in after] + [i.pack for i in imported_after if i.id]
    return [f'Nothing changed: {", ".join(p.name + at(p) for p in pins) or "no packs installed"}']
