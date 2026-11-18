---
name: pack-findings
description: Find where a PR, branch or commit range deviates from a repo's context packs, whether each rule's `when` reached the work, and the choices it makes that no rule covers. Run by the `pack-review` skill, which goes through the findings with the user.
argument-hint: "[PR number or owner/repo#number, branch, or commit range]"
---

# Pack findings

Done when:

- every doc the repo puts in front of an agent was read in full against the diff;
- every deviation from a rule quotes the rule and the line that deviates from it, says whether the rule's doc was routed to the work, and gives any signs the deviation is deliberate;
- the diff was read for choices no rule covers, and each uncovered choice says how the existing code makes it;
- every finding was handed over in the shape [findings.schema.json](https://github.com/mjewell/context-packs/blob/main/review/findings.schema.json) sets, to whoever ran this skill, as described in [Where it runs](#where-it-runs).

This checks the change only against what the repo's packs and instruction file say. Bugs, and whether the change does what it set out to do, are for other reviews. Deciding what to do about each finding is for `pack-review`.

Each finding is one of three kinds:

- **Deviation**: the change deviates from a written rule. The change may be wrong, the rule may lack an exception, or the convention may have moved on. The diff can't tell which, so the user decides. Each deviation also says whether the rule's doc was routed, meaning its `when` matches the work.
- **Conflict**: two rules point opposite ways at the same spot.
- **Uncovered choice**: the change makes a kind of decision that will come up again, another way would be reasonable, and no rule covers it.

## Where it runs

- **Run by another skill**, such as `pack-review`: every step below, then hand back the findings. Don't show them to the user or ask about them. Once you've handed them back, carry on with that skill's next step.
- **Run by the user**, with a PR, branch or range: every step below, then show the findings. Give the number of each kind, then each finding in full, grouped by kind. Say that running `pack-review` in this session goes through them, without finding them again.

A PR named as `owner/repo#number` is in that repo: from a folder above the repos, work in its checkout.

## 1. Pin the diff

Resolve what you were given to a base and a head: a PR's base and head, a branch against the default branch, or a range as given. For a GitHub PR, `git fetch origin pull/<number>/head` gets the head. Then capture:

```bash
git diff <base>...<head>
git log --oneline <base>..<head>
```

Stop if a ref doesn't resolve or the diff is empty. Read the packs as they are at the head, so a change that updates a rule along with the code is judged by the new rule. Note any changes the diff makes to the packs, for whoever reads the findings.

## 2. List the units

Run `npx context-packs docs` in the repo. It prints every doc the tables point at, with a blank line between packs. The units are the instruction file, whole, then the docs each pack's table points at, in the order it prints them. Each file is read by exactly one unit. One more subagent, the uncovered finder, has no unit: it reads the whole diff for choices no rule covers, and searches every unit's docs. The instruction file holds its own rules, and the pack rules of every pack inlined in the context-packs block. A nested pack's index holds that pack's pack rules, and the pack rules of any pack inlined in it. Done when you have the units' paths.

## 3. Dispatch the units

Launch one subagent per unit and the uncovered finder, all in one message, so they run at the same time. Don't read the docs or the diff yourself: each is read by the subagent that checks it. Give each unit's subagent exactly the prompt in [unit-prompt.md](unit-prompt.md), and the uncovered finder exactly the prompt in [uncovered-prompt.md](uncovered-prompt.md). Replace `{docs}` with the unit's paths, or every unit's paths for the uncovered finder, each on its own line as ``- `path` ``. Replace `{diff}` and `{log}` with the diff and log as your run has them: a file, or the git command.

Wait until every subagent has answered before you go on. A subagent running in the background reports when it's done.

## 4. Merge their answers

Merge the subagents' answers as [merge-prompt.md](merge-prompt.md) says, with `{answers}` read as "The finders' answers are the subagents' answers." CI runs the same three prompts, so a local review and a CI review check the same way.
