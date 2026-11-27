# Skills that grow your packs

Two skills help write the rules themselves. `npx skills add mjewell/context-packs -g` installs them with the `context-packs` skill. Pick with `-s`, such as `-s context-packs` for just that one.

- **`pack-rule`** writes one rule into the repo's packs, from a pattern you describe or examples you point at. It looks for a rule that already covers it first, and updates that one rather than adding another. Ask things like "Document that API handlers validate input with Zod".
- **`pack-backfill`** finds one decision the code makes that no rule settles yet, asks you to confirm it, and writes it with `pack-rule`. It's meant to be cheap enough to run often. In Claude Code, run `/pack-backfill`, or `/pack-backfill src/billing` to look in one area.

## Spec trees

**`spec-tree`** keeps a spec tree: a nested outline of how one part of a system works and why, which you read from the top and expand where you need detail. Agents update the tree in the same PR as the code, so its diff shows what changed in the design. The skill holds the spec and a CLI that checks a tree against it, measures it, and renders it as a page that starts collapsed. Install just this one with `npx skills add mjewell/context-packs -g -s spec-tree`.
