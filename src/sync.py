"""Writing packs into a folder: each pack's docs and generated indexes, and the instructions file's text with a
block for each pack after the header block."""
import shutil

from blocks import HEADER, HEADER_RULES, HEADER_START, block, snapshot
from packs import PACKS
import tree


def write(repo, found, packs, folders, roots):
    """Write each pack's files into repo from the folder holding its content, and return the instructions file's
    text, with the blocks found in it replaced by the header block and a block for each pack, and those blocks by
    name."""
    blocks = {HEADER: block(HEADER_START, HEADER_RULES)}
    for pack in packs:
        root = roots[pack.name]
        generated = repo / PACKS / pack.name
        if generated.exists():
            shutil.rmtree(generated)
        tree.write(root, pack, folders[pack.name], repo)
        blocks[pack.name] = block(pack.start(), tree.body(root, pack), snapshot(generated))
    if (repo / PACKS).is_dir() and not any((repo / PACKS).iterdir()):
        (repo / PACKS).rmdir()
    return found.text[:found.start] + '\n'.join(blocks.values()) + found.text[found.end:], blocks
