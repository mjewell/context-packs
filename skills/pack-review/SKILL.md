---
name: pack-review
description: Review a PR or branch against a repo's context packs. Find where it breaks a written rule, and the gaps in the packs it shows, such as a rule its doc's `when` didn't reach or a choice no rule settles.
argument-hint: "[PR number, branch, or commit range]"
disable-model-invocation: true
---

# Pack review

Done when:

- every doc the repo puts in front of an agent was read in full against the diff, by you or a subagent;
- every violation reported quotes the rule it breaks and the line that breaks it, and says whether the rule's doc was routed to the work;
- the diff was walked for choices no rule covers, and each such gap says how the existing code makes that choice;
- the user has seen a summary of every finding and gone through them one at a time;
- each gap the user accepted was handed to the `pack-rule` skill, one per run.

This review checks the change only against what the repo's packs and instruction file say. Bugs, style no rule mentions, and whether the change does what it set out to do are for other reviews. A finding with no rule to quote is either a gap or out of scope.

A **violation** is a place where the diff breaks a written rule. It gets fixed in the change. A **gap** is knowledge the packs are missing, or hold in a way that didn't work:

- **Unreachable**: the diff breaks a rule whose doc's `when` doesn't match the work. The fix is the `when`, not the rule.
- **Weak**: the diff breaks a rule whose doc's `when` does match, and the wording would let an agent read it and still go the other way.
- **Stale**: the change deliberately moves away from a convention a rule still describes.
- **Conflicting**: two rules point opposite ways at the same spot.
- **Unsettled**: the change makes a choice an agent would copy, another way would be reasonable, and no rule covers it.

## 1. Pin the diff

Resolve what the user named to a base and a head: a PR's base and head, a branch against the default branch, or a range as given. For a GitHub PR, `git fetch origin pull/<number>/head` gets the head. Then capture:

```bash
git diff <base>...<head>
git log --oneline <base>..<head>
```

Stop if a ref doesn't resolve or the diff is empty. Read the packs as they are at the head, so a change that updates a rule along with the code is judged by the new rule. Note any changes the diff makes to the packs, for the summary.

## 2. Map what an agent would have read

Collect everything the repo puts in front of an agent: the rules inlined in the instruction file, every doc its tables list, the indexes of nested packs and their docs in turn, and any doc the instruction file points at outside the context-packs block, such as a hand-kept list of docs, a glossary or ADRs.

Build the **routing map**: for each doc, whether its `when` matches the work in the diff, and which change it matches. Judge from the `when` lines and the instruction file alone, as the author's agent would have before opening any doc.

Group the docs into **units** for checking. Each pack is a unit, holding its own docs but not its nested packs. The instruction file's own rules and the docs outside the block form one more. Split a unit whose docs are more than one agent can read closely alongside the diff, and merge small ones. Done when every doc is in exactly one unit.

## 3. Check each unit against the diff

Give each unit to a subagent, all in parallel. A single small unit can be checked inline. Each one gets the diff and log commands, its docs' paths, and their routing. It reads every doc in full, whatever its routing, since the docs that didn't route are where unreachable rules show up.

For each rule that applies somewhere in the diff, it returns a **ledger** entry:

- the rule, quoted, with its file;
- where it applies in the diff, as file and line;
- whether that spot follows the rule, breaks it, or moves away from it on purpose so the rule is now stale;
- whether the rule's doc was routed.

It reports nothing it can't quote a rule for. Done when every unit has reported. Merge their entries into one ledger.

## 4. Look for unsettled choices

After step 3, one subagent walks the diff hunk by hunk with the merged ledger. It looks for choices an agent would copy, where another way would be reasonable, that no ledger entry covers: where a kind of logic lives, how a kind of file is shaped, which library or style it uses, how errors travel, how a kind of thing is named. It leaves out choices with no real alternative, what a linter, formatter or type check enforces, and one-off logic.

For each choice, it finds how the existing code makes it, with two or three **exemplars** of each way:

- **A second way beside an existing one** is the strongest candidate, since an agent copies whichever way it reads first.
- **The code's one existing way**, followed again, needs a rule of fewer words.
- **A choice made for the first time**, such as a new kind of file or extension point, is worth a rule if more like it will follow.

Before reporting a choice, it searches the docs for a rule that settles it, by meaning as well as by keyword. If one does, the choice belongs in the ledger instead.

The walk isn't exhaustive. A missed gap turns up in a later review or a `pack-backfill` run, while each weak candidate costs the user a turn. Report the strongest few.

## 5. Sort the findings

From the ledger:

- Each broken rule is a violation. If its doc wasn't routed, it's also an unreachable gap. If it was routed, it's a weak gap only when the wording leaves room to go the other way. A routed, clear rule that was broken is just a violation.
- Each stale entry is a stale gap.
- Two entries on the same spot that point opposite ways are a conflicting gap.

Add the unsettled choices from step 4. Merge findings that two units reported about the same spot.

## 6. Report

Start with a summary: the number of violations and gaps, and a line for each, violations first. Then go through them one at a time. For each, quote the rule or the hunk, give your take, and wait for the user before moving on.

Keep the review in chat. Posting it to the PR writes to an external system: do it only if the user asks, and show them the comments first.

## 7. Hand off the gaps

Hand each gap the user accepts to the `pack-rule` skill, one per run. Pass its kind, the ledger entries or hunks behind it, its exemplars, and the user's answer on which way new code should follow. Leave the violations for the change's author, unless the user asks you to fix them.
