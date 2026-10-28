---
name: pack-backfill
description: Find one decision a repo's code makes, consistently or not, that its context packs don't settle, and write it in. Cheap enough to run often.
argument-hint: "[area of the code, or kind of rule, to look for]"
disable-model-invocation: true
---

# Pack backfill

Done when the user has accepted one unsettled convention and it has been written with the `pack-rule` skill.

The packs grow by many small rules over time, so each run should cost little: skim rather than survey, and stop at the first candidate worth writing.

A **convention** is a decision the code makes, consistently or not, where there's a reasonable argument for another way: where a kind of logic lives, how a kind of file is shaped, which of two libraries or styles to use, how errors travel. When the code makes a decision several ways, an agent copies whichever it reads first, so prefer those candidates. A decision is still a candidate when an agent would make it the same way today, since another agent or model might not; its rule just needs fewer words. Leave out what has no real alternative, what a linter, formatter or type check already enforces, and practices the code doesn't show at all.

## 1. Find a candidate

Look in the area, or for the kind of rule, the user named. Otherwise pick somewhere busy that the docs say little about: compare the folders recent commits touch most with what the docs' `when` lines and topics cover, and start in the busiest one nothing covers. Read a handful of files and the last few commits there until you see a decision made in several places, the same way or not. Note two or three **exemplars** of each way, recent files worth copying, and any **counterexamples**.

Search the instruction file and the docs it points at for that decision, by meaning as well as by keyword. If a rule already settles it, look for another. Done when you have a candidate nothing settles.

## 2. Ask the user

Show them the decision in a sentence with its exemplars and any counterexamples.

- **Made one way**: ask them to confirm it's the pattern new code should follow.
- **Made several ways**: show each way with its exemplars, how many places follow it and which one recent commits grow, then the tradeoff between them, what each buys and costs in this code. Ask which new code should follow.

If they pass on it, go back to step 1 for another.

## 3. Write it

Hand it to the `pack-rule` skill with the user's answer and the evidence. When the user picked between several ways, the rule names the others as older patterns new code shouldn't copy, describing them rather than listing the files that follow them.
