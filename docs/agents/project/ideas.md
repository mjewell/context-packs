---
when: Changing how a repo chooses which of a pack's docs it installs
---
# Ideas not built yet

## Packs as the unit of choice

Instead of optional doc sets within a pack, optional docs could ship as packs of their own: agent-config would hold `context/core/` and `context/typescript/`, and a repo would add the ones it wants. Every pack would then install all its doc sets, as a pack in the synced repo already does, so the `tier` field, the `docs` command, `--docs` and tracking which sets a repo chose could all go, and local and remote packs would behave the same. The cost is a block and a pin for each optional pack a repo installs. It's unclear whether a pack would still want required and optional sets within it.

## A folder of packs

A repo could add a folder holding several packs, such as `context/` holding `core/` and `typescript/`, to get all of them at once, while another repo adds just `context/core`. The tool would need to tell a folder of packs from a pack whose doc sets are folders, which their contents alone can't settle: a pack with no `agents.md` and only folders looks like either. It would also need to decide whether the parent folder becomes one block or one per pack inside it.
