# Skills that grow your packs

Four skills help write and apply the rules themselves. `npx skills add mjewell/context-packs -g` installs them with the `context-packs` skill. Pick with `-s`, such as `-s context-packs` for just that one.

- **`pack-rule`** writes one rule into the repo's packs, from a pattern you describe or examples you point at. It looks for a rule that already covers it first, and updates that one rather than adding another. Ask things like "Document that API handlers validate input with Zod".
- **`pack-backfill`** finds one decision the code makes that no rule settles yet, asks you to confirm it, and writes it with `pack-rule`. It's meant to be cheap enough to run often. In Claude Code, run `/pack-backfill`, or `/pack-backfill src/billing` to look in one area.
- **`pack-findings`** checks a PR or branch against the repo's packs. It reports where the change deviates from a rule, whether that rule's `when` reached the work, and choices the change makes that no rule covers. In Claude Code, run `/pack-findings my-branch` to see them.
- **`pack-review`** goes through those findings with you. You decide whether the change or the rule needs fixing, and each rule to record goes to `pack-rule`. It runs `pack-findings` itself, so `/pack-review 42` for a PR, or `/pack-review my-branch`, does both. The `review` action runs `pack-findings` on each PR in CI and posts what it finds, for the author to go through in a local session: see [Reviewing PRs in CI](reference.md#reviewing-prs-in-ci).
