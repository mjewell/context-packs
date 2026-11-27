# context-packs

Shared agent rules and docs, kept in git repos and synced into each repo's instruction file.

## Packs

**Pack**:
A collection of pack rules and pack docs that can be synced into a repo's instruction file.

**Import pack**:
A folder the repo owns, holding only a `pack.md`, that names a pack kept elsewhere, and the commit or tag it's pinned to when it comes from git. Its `pack.md` can also set the pack's `when`, and add pack rules of its own, but no docs.

**Pinned**:
Said of a pack from git, held at a commit or tag until someone runs `update`. Its docs are copied into `context-packs/gen/`.

**Read in place**:
Said of a pack in a folder on disk, such as the repo's own docs. It isn't pinned, and its table points at its docs where they are.

**Rule**:
One instruction to agents, in a pack, a doc, or the instruction file. Not a Claude Code rule, which is a file in `.claude/rules/`, or a Codex rule, which decides whether a shell command may run.

**Pack rules**:
The rules in a pack's `pack.md`. They load wherever the pack does: where its parent's are when it's inlined, in its own index otherwise.
_Avoid_: "a pack's rules" or "its rules" for these, since a pack's docs hold rules too

**Pack doc**:
A file of rules in a pack, which an agent reads only when its `when` matches the work. Plain "doc" is fine where a pack, a `when` or `context-packs docs` makes that meaning clear.
_Avoid_: context doc; doc on its own, where a repo's other docs could be meant

**`when`**:
The line saying what work a doc or pack applies to. A pack whose `when` is `always` is inlined.

**Table**:
A pack's list of what to read for which work, written after its pack rules. Each row gives a `when`, and the path of a doc, or of the index of a pack inside it that isn't inlined.

**Instruction file**:
The `AGENTS.md` or `CLAUDE.md` a repo's agents read first.

**Block**:
The part of the instruction file the sync writes, between its markers.

**Inlined**:
Said of a pack whose pack rules are written where its parent's are, in the block or in its parent's index, rather than behind a row of its own.

**Top-level pack**:
The pack that `context-packs/` itself is, whose pack rules are inlined into the block.
_Avoid_: root pack, top pack, the pack at the top

**Index**:
A doc the sync writes for a pack that isn't inlined, holding its pack rules and table. The pack's row points at it.

**Check**:
`context-packs check`, which fails when a sync would change anything.
