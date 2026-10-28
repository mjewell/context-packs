---
name: pack-rule
description: Write a pattern or convention into a repo's context packs, generalized from examples, updating the rule that already covers it rather than adding a duplicate. Use when asked to document a pattern or convention, add or change a rule or context doc, or when another skill hands over a candidate rule.
---

# Pack rule

Done when:

- the rule lives in one place among the packs the repo loads: the rule already covering it was updated, or, where none did, a new one was added;
- it covers every example found, excludes every counterexample, and says why, describing the pattern in general terms rather than pointing at files that show it, since files move and change;
- an agent doing the work it governs would follow it: the rule reaches the agent, inline or through a doc whose `when` matches that work, with an eval prompt to check, and says plainly enough what to do that the agent acts on it;
- the repo is resynced, and the user has approved the wording and seen what changed, left uncommitted.

One rule per run. A skill with several candidates hands them over one at a time.

## 1. Pin down the pattern

Start from what you were given: a description, examples, counterexamples, or a candidate with its evidence. Search the code for more of each until you can state the boundary: which code follows the pattern, which deviates on purpose, and which is legacy that new code shouldn't copy. Done when the rule fits in a sentence or two with its reason, and every example lands on the right side of it. Two or three examples generalize easily to something broader than the user meant, so where they don't settle the boundary, ask.

If a linter, type or test could enforce the rule, such as a banned import, a naming scheme or where a file goes, say so and offer that alongside the doc, or instead of it: a check runs every time, and a doc only when it's read.

## 2. Find what already covers it

Read everything the repo puts in front of an agent: the instruction file holding the context-packs block, every doc its tables list, the indexes of nested packs with their docs in turn, and any doc the instruction file points at outside the block, such as a hand-kept list of docs, a glossary or ADRs. Look for the rule by meaning, since an existing one may use other words. Done when you can say which of these holds, citing the file:

- **Covered**: a rule says this already. Stop and tell the user, unless the session shows an agent went against it. If the agent never read the doc, the rule is unreachable. If it read it and went the other way anyway, the wording is too weak: sharpen it, as for a partial rule.
- **Unreachable**: a rule says this, but its doc's `when` doesn't match the work it governs. Fix the `when` rather than the rule.
- **Partial**: a rule says something close, broader or narrower. Extend or sharpen it rather than adding another beside it.
- **Contradicted**: a rule says otherwise. Show the user both and ask which wins.
- **New**: nothing covers it.

## 3. Choose where it goes

Edit a rule only at its source. The block in the instruction file and everything under `context-packs/gen/` are generated, and the next sync stops if they were edited. A doc under `context-packs/gen/<id>/` came from the import pack `context-packs/<id>/pack.md`, and its `from` and `path` say where the source is:

- **No import pack**: a doc or `pack.md` in `context-packs/` is the repo's own. Edit it there.
- **`path` only, or `from` a folder**: the pack is read from disk. Edit it in that folder. A folder outside the repo is another repo, with its own rules to read first.
- **`from` a git URL**: the pack is pinned, and its source isn't here. Give the user the choice:
  - Change it at its source, if they own that pack and have a checkout of it: edit there, and once it's pushed, `update <id>` here. Pushing is theirs to approve.
  - Add a local rule that refines it, naming the rule it refines. It works now, and can move upstream later.
  - For an unreachable rule, a local `when` in the import pack overrides the row of the pack's root, but not the rows of the docs inside it.

For a new rule, follow the repo's instruction files if they say where rules go. Otherwise it goes in the repo's own packs:

- the doc whose `when` already covers the work it governs;
- else a new doc, `context-packs/<name>.md`, or in the folder of the area it belongs to;
- in `context-packs/pack.md` only if it bears on most tasks, since every session loads it.

Where the repo already keeps docs of its own outside its packs, such as a folder its instruction file lists by hand, offer the one a rule would join as another option. Recommend the packs anyway when a `when` would reach the rule more reliably than the hand-kept pointer.

A rule that isn't specific to this repo can move to a shared pack later. Mention that when the user owns one, and start it here.

Done when the user has picked wherever there was a choice.

## 4. Write it

Write in the voice of the docs around it. State what to do and the reason, and fold a sharpened rule into the existing text rather than appending a caveat. A new doc starts with front matter whose `when` names what the agent will be doing or touching, as a path glob or a kind of task:

```markdown
---
when: Editing `src/billing/**`
---
```

Widen an existing doc's `when` if the rule widens what the doc covers. Show the user the change, and revise until they approve it.

## 5. Make it reachable

For a new doc or a changed `when`, add prompts to the evals of the pack holding the doc, in `.evals/` at that pack's root, named by the doc's path in it: `context-packs/.evals/billing.md` for `context-packs/billing.md`. Under `## Reads`, a prompt like the work that should find the rule, such as the one where an agent missed it. Under `## Skips`, one close to it that shouldn't:

```markdown
## Reads

- Add a refund endpoint to the billing API.

## Skips

- Rename the billing page's heading.
```

Running them costs tokens, so offer `npx context-packs eval <doc>` and run it only if the user agrees.

## 6. Resync and report

Resync with `npx --yes context-packs`, or with the `context-packs` skill if it stops with an error. Report what changed, from `git status`, and leave it uncommitted.
