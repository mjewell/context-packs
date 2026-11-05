---
name: pack-review
description: Review a PR or branch against a repo's context packs. Find where it deviates from a written rule, whether that rule's `when` reached the work, and the choices it makes that no rule covers.
argument-hint: "[PR number, branch, or commit range]"
disable-model-invocation: true
---

# Pack review

Done when:

- every doc the repo puts in front of an agent was read in full against the diff, by you or a subagent;
- every deviation from a rule quotes the rule and the line that deviates from it, says whether the rule's doc was routed to the work, and gives any signs the deviation is deliberate;
- the diff was walked for choices no rule covers, and each uncovered choice says how the existing code makes it;
- the user has seen a summary of every finding, gone through them one at a time, and said what to do about each;
- the `pack-rule` skill was run once for each finding the user wants recorded in the packs.

This review checks the change only against what the repo's packs and instruction file say. Bugs, and whether the change does what it set out to do, are for other reviews.

Each finding is one of three kinds:

- **Deviates**: the change deviates from a written rule. The change may be wrong, the rule may lack an exception, or the convention may have moved on. The diff can't tell which, so the user decides. Each deviation also says whether the rule's doc was routed, meaning its `when` matches the work.
- **Conflicting**: two rules point opposite ways at the same spot.
- **Uncovered**: the change makes a kind of decision that will come up again, another way would be reasonable, and no rule covers it.

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

Give each unit to a subagent, all in parallel. A single small unit can be checked inline. Each one gets the diff and log commands, its docs' paths, and their routing. It reads every doc in full, whatever its routing, since a rule whose doc didn't route can still apply to the change.

For each rule that applies somewhere in the diff, it returns one **ledger** entry:

- the rule, quoted, with its file;
- whether the rule's doc was routed;
- every spot in the diff where the rule applies, as file and line, each saying whether it follows the rule or deviates from it;
- for each deviating spot, any signs it's deliberate: a comment at the spot, a condition in the code that sets the spot apart, or the PR description or commit messages saying so.

Spots that all deviate the same way are a sign too, and spots that mix following and deviating show the change isn't consistent with itself. It reports signs, not a verdict on whether the deviation is right.

It reports nothing it can't quote a rule for. Done when every unit has reported. Merge their entries into one ledger, kept by rule. The gap pass and the check for conflicts read it by spot instead: for each hunk, the rules that apply to it.

## 4. Look for uncovered choices

After step 3, one subagent walks the diff hunk by hunk with the ledger arranged by spot. It looks for kinds of decision that will come up again, where another way would be reasonable, that no ledger entry covers: where a kind of logic lives, how a kind of file is shaped, which library or style it uses, how errors travel, how a kind of thing is named. It leaves out choices with no real alternative, what a linter, formatter or type check enforces, and one-off logic.

For each choice, it finds how the existing code makes it, with two or three **exemplars** of each way:

- **A second way beside an existing one** is the strongest candidate, since an agent copies whichever way it reads first.
- **The code's one existing way**, followed again, needs a rule of fewer words.
- **A choice made for the first time**, such as a new kind of file or extension point, is worth a rule if more like it will follow.

Before reporting a choice, it searches the docs for a rule that settles it, by meaning as well as by keyword. If one does, the choice belongs in the ledger instead.

The walk isn't exhaustive. A missed choice turns up in a later review or a `pack-backfill` run, while each weak candidate costs the user a turn. Report the strongest few.

## 5. Sort the findings

From the ledger:

- Each entry with a deviating spot is one deviates finding, listing those spots and carrying whether its doc was routed.
- Two entries that share a spot and point opposite ways are conflicting.

Add the uncovered choices from step 4. Merge findings that two units reported about the same rule.

## 6. Report

Start with a summary: the number of findings of each kind, and a line for each. A deviation's line says whether its doc was routed. Then go through them one at a time. For each, quote the rule or the hunk, give any signs the deviation is deliberate, give your take, and wait for the user to say what to do:

- **Deviates**: fix the change, or change the rule by sharpening its wording, adding the exception the change shows, or replacing it. When the rule's doc wasn't routed, its `when` may also need fixing, whichever way the rest goes.
- **Conflicting**: which rule wins.
- **Uncovered**: whether to write it, and which way new code should follow.

Keep the review in chat. Posting it to the PR writes to an external system: do it only if the user asks, and show them the comments first.

## 7. Hand off what to record

Run the `pack-rule` skill once for each finding the user wants recorded in the packs, since it writes one rule per run. Pass it the finding's kind, whether its doc was routed, the ledger entries or hunks behind it, any signs of a deliberate deviation, its exemplars, and the user's answer. Leave fixes to the change for its author, unless the user asks you to make them.
