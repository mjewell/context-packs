---
when: Drafting an overview or diagram of how a system or codebase works, such as a page or diagram of its flows, its parts, or how its files connect
---
# System overviews

An overview shows a system's shape, so a reader can talk about how it works and see where a change might pay off. Edge cases and full reasons stay in the spec and the code. Start everything small, so the structure reads at a glance, and let the reader open any part to see how it behaves.

## Behaviour

- Lead with one map of the whole system that fits on a screen: its parts as boxes, and who talks to whom as arrows. Clicking a part shows a one-line definition, and links to the flow that shows it step by step. Define each term that has no box in one line under the map. A list of parts says less than their interactions.
- Show each common flow as a sequence diagram: a lane per party, an arrow per message and reply, and a tab per flow.
- Show each variation as a change to the typical path: highlight the steps it adds, and fade the steps it skips. The reader learns the common path once, and reads each variation as a difference from it.
- Each step reads as one line. Opened, it shows at most three lines of pseudocode: what the step refuses, what state it writes, and what it hands back. Add a reason only where the code doesn't make it clear. Offer a way to open every step at once.

## Code

- Group files by which entry points reach them, worked out from the imports rather than drawn by hand, so the groups are facts about the code.
- Draw only the import edges that decide a file's group: without the edge, the file would still be reached, but from one side only. Those are the imports worth questioning. A full import graph is too much to read, and tags such as "imports only types" end up on most edges.
- Let the reader put one file in the middle, with what it imports on one side and what imports it on the other. Each edge names what it takes and why.
- Treat a script's commands and a class's methods as its interface. Give each its own block, which opens to its pseudocode, whether or not it's exported.

## Leave out

- Tables that cross every behaviour with where it lives, or list every command or state file. They're complete but not skimmable, and the spec already holds that detail.
- Lists of candidate changes. Those come up in a conversation about the overview, not in the overview.
