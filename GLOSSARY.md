# context-packs

Shared agent rules and docs, kept in git repos and synced into each repo's instruction file, and the review that checks a change against them.

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
_Avoid_: CI check, for the review

## Review

**Review**:
Checking a change against a repo's packs and instruction file, to produce findings. It's either a CI review or a local review.

**CI review**:
A review the workflow runs on a PR, which posts its findings for pack-review.
_Avoid_: pack-review, review action, CI check

**Local review**:
A review pack-review runs in the author's session, through pack-findings, for a change that CI didn't review.

**pack-review**:
The skill an author runs locally to go through a PR's findings and decide each one.
_Avoid_: using it for the CI review, or for the identity that posts the CI review's comments

**Unit**:
The docs one finder checks: the instruction file, or the docs one pack's table points at.

**Finder**:
An agent that checks a diff against one unit, or the uncovered finder.

**Uncovered finder**:
The finder with no unit, which reads the whole diff for uncovered choices and searches every unit's docs for a rule that settles each one.

**Group**:
The merging agent's answer for one finding: the ids of the finders' findings it merges, with its kind, headline and take.

**Wizard**:
The command an agent runs a review through, one step at a time: `context-packs review`, which the pack-findings skill runs in a local review and in CI alike. Each step prints what to do next, with every command in full. It's a state machine: its state is which files the run folder holds, and it refuses a step whose checks fail.
_Avoid_: script, orchestrator (the agent that runs it)

**Orchestrator**:
The agent that runs the wizard's `init` and `next`, and starts the subagents they name.

**Run folder**:
The folder `init` makes for one review, which holds its state, the agents' answers and the findings. Every command the wizard prints names it.

**Brief**:
The prompt the wizard gives one finder, or the merging agent: the skill's prompt for it, with the commands it reads through and where its answer goes.

**Served doc**:
A doc the wizard printed through `doc`. A unit's answer is taken only once every doc in the unit was served.

**Finding**:
One choice in a diff that the review reports. It is a deviation, a conflict or an uncovered choice.

**Deviation**:
A finding where the change goes against a written rule.

**Conflict**:
A finding where two rules point opposite ways at the same spot.

**Uncovered choice**:
A finding where the change makes a kind of decision that will come up again, another way would be reasonable, and no rule covers it.

**Routed**:
Said of a doc whose `when` matches the work in the diff.

**Summary**:
The one comment a CI review keeps on a PR, counting the findings and carrying every finding for pack-review.

**Review thread**:
A thread on the diff that a CI review opened for one finding.

**Pairing**:
Deciding, in one CI review, which finding is about the same issue as which review thread. Each finding and each thread is in at most one pair, and a thread pairs with a finding from each CI review that finds its issue again.
_Avoid_: matching, continuing

**Commentary**:
What a CI review tells the author about a review thread's replies, when they give the author a reason to act.
