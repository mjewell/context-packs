# Why not symlinked rules?

Claude Code's `.claude/rules/` [follows symlinks](https://code.claude.com/docs/en/memory#share-rules-across-projects-with-symlinks), so linking each repo's rules to one shared checkout looks simpler than a sync. But rules linked from outside the repo load poorly:

- **They wait for approval.** They load only after someone approves external imports for the project, in a dialog at the start of an interactive session. Decline it once and they stay off, with no further prompt.
- **Path-scoped rules never load.** Even after approval, a linked rule with a `paths` field is skipped.
- **Only Claude Code reads them.** Codex and agy read `AGENTS.md`, not `.claude/rules/`.
- **The links resolve only where the shared repo sits at the same path.** Every teammate, CI runner and cloud session needs that checkout. A synced pack is committed into the repo, so it works wherever the repo is checked out.
- **Changes skip review.** An edit to the shared repo reaches every linked repo at once. A sync lands as a diff in each repo, reviewed like any other change.
