# Design Trees: spec v0

Nov 18, 2026 · @Michael Jewell

## Purpose

A design tree is a nested outline of how one part of a system works and why, kept small enough at every level to skim. You read the top level for the overall shape and expand only the branches you care about, down to the finest details of behavior and decisions at the leaves.

Design trees exist so a person can keep up with code that agents write. Agents update the tree in the same PR as the code, so the tree's diff is a readable changelog of design changes.

Agents maintain the trees, not people. Rebalancing nodes on every change is too tedious for humans, so these rules assume an agent does it, with tooling to measure sizes. People read, review and occasionally edit.

The approach borrows from three older ideas: Ted Nelson's stretchtext (text that expands in place), Barbara Minto's pyramid principle (parents summarize children) and Robert Horn's Information Mapping (bounded chunk sizes).

## Scope

A tree holds everything needed to reimplement the system without its code, and nothing about how the current code is written. From the tree alone, someone could build a system that behaves the same and was designed for the same reasons, even though their code would differ.

- **In the tree:** purpose, components and their boundaries, external interfaces and contracts, behavior down to edge cases, limits and error handling, constraints such as performance targets, and the reasons and rejected alternatives behind each.
- **In the code:** how it is written, meaning module and function structure, naming, patterns, data structures and optimizations. Decisions at that level are code comments, because the code is a standalone artifact.
- **The test:** would a correct reimplementation have to match this? If yes, it goes in the tree. If a different implementation could do it differently and still be right, it stays in the code. For example, staying under GitHub's API rate limit goes in the tree, while batching calls to do it stays in the code.

The deepest levels are a full spec of today's behavior. Most readers stop long before them; people and agents changing a piece read down that far.

## Model

A tree is a hierarchy of nodes, where each node has a short text, zero or more children and exactly one parent (except the root). Something used in two places lives in one and is linked from the other. Nobody chooses the depth: it comes from the size rules, so a small topic stays one flat list and a large one grows levels as content is added.

- **Root:** the tree's title plus one sentence saying what it covers.
- **Node text:** the words a node shows when its parent is expanded.
- **View:** a node's own text plus the text of its direct children, which is what a reader sees after expanding it once.
- **Subtree size:** total words in a node and all its descendants.
- **Leaf:** a node with no children.
- **Word count:** whitespace-separated words after removing markup. Labels, IDs, links, code paths and diagrams don't count.

## Size rules

Size rules decide when the structure changes. They are approximate and checked with tolerance.

| Rule | Target | CI warns | CI fails |
| --- | --- | --- | --- |
| Node text | ≤ 40 words | > 40 | > 60 |
| Children per node | ≤ 7 | > 7 | > 10 |
| View (node + direct children) | ≤ 150 words | > 150 | > 225 |
| Nested subtree size | > 60 words | ≤ 60 | Never |

- **Nest** when an edit would push a view past 150 words or 7 children. Move detail down a level: shorten some children into summaries and give them children of their own, or group children under new intermediate nodes.
- **Flatten** when a nested subtree drops to 60 words or fewer. Pull its descendants up into one level, because nesting something that small only costs clicks.
- **Leave it alone** between those thresholds. A subtree of 60 to 150 words may be flat or nested, and doesn't change shape until a threshold is crossed. This gap is the hysteresis: it stops a node near the line from flipping shape on every edit.
- **New content starts flat.** Nest only when a threshold forces it.

Files have a coarser budget with the same hysteresis. Promote a subtree into its own file when a file passes \~1,500 words (CI fails at 2,250), and merge it back when it falls under \~500.

The numbers are v0 starting points, to tune after a few real trees exist.

## What stays up

Size decides when to push detail down. A fixed priority order decides what goes down first.

1. **Purpose and shape:** what this is and what it's made of.
2. **How it works:** behavior, rules and contracts.
3. **Why this way:** rationale and constraints.
4. **Rejected alternatives:** what we chose not to do, and why.

When nesting, push the lowest-priority material down first. An agent may break the order when a lower item matters most to a reader skimming that level, for example a contested decision where the rejected option is the main story.

**Parent rule.** A parent must not contradict its children or claim anything they don't support. It doesn't have to mention every child: it should convey the most useful information from its subtree that fits its budget, and anything left out is one expansion away. Avoid parents that only restate their children's first lines.

An edit deep in the tree can make an ancestor wrong, so a content change is finished only when the edited node's ancestors are accurate again.

**Parallel rule.** When a node lists cases of one kind, such as the kinds of a thing or the steps of a flow, each case is its own child. Anything said about one case goes under that case, not beside the cases as a sibling, so every case expands the same way.

## Format

A tree is a directory named `<id>.tree/`, kept next to the code it describes. It holds only Markdown, plus the page the renderer writes beside the root file: most trees are one file of nested bullets, and large ones spread across files that mirror the tree (see Files below).

```markdown
# Review agent {#review-agent}

Every PR gets an automated first-pass review before a human looks.

- Runs as a GitHub Action when a PR is opened or updated {#review-trigger}
  - Why: reviewing every push was noisy and expensive
  - Rejected: a nightly batch, because feedback came too late
- Reads the design trees for the files it touches, see [[tree-lookup]]
```

- **Root:** an H1 title with the tree's ID, then one sentence on what the tree covers, then the top-level bullets. Front matter is allowed but ignored, and the spec reserves no keys.
- **Nesting:** two-space indent per level.
- **Labels:** a node may start with `Why:` or `Rejected:`. Unlabeled nodes say what something is or how it works. Labels let readers and tooling spot decisions. A labeled node is about its parent. `Why:` gives a reason for the parent's claim, and `Rejected:` names an alternative to it. In a promoted file, a top-level labeled node is about the promoted node.
- **Reasons:** a short reason the claim doesn't read without stays inline, as in "…, since a review comment needs a line in the diff". A reason gets its own `Why:` node when it's evidence or history, such as what went wrong before, or when inline it would push the node past its size.
- **One decision per node:** a node may have several `Why:` children when they're separate reasons for the same claim. When they justify different decisions in one node, split it so each decision has its own node.
- **IDs:** `{#slug}` at the end of a node's text. A node has at most one, and only nodes that something links to need one. IDs are unique across the repo and stay with the node when it moves. When a node's meaning changes, rename its ID: every incoming link breaks, and the checks force each one to be revisited.
- **Links:** `[[slug]]` points at a node in any tree in the repo. Links target IDs, never positions or files, so moving a node never breaks a link. A link is a jump, not an expansion: expanding a node shows its own children, never a linked node's children. Depth follows parent-child edges only, so cycles through links are harmless.
- **Merges and deletes:** when two nodes merge, the merged node keeps whichever existing ID fits it, or gets a new one when neither does. Merging, deleting or renaming a node means fixing its inbound links in the same commit. `links-to <id>` lists them, and the link check fails on any left over.
- **Diagrams:** a node may hold a diagram as a fenced code block, indented under its text. The diagram belongs to the node and isn't one of its children. Put it on the node whose structure it shows, so expanding that node shows the picture beside the children it describes. Any diagram language works. Mermaid renders on GitHub, and other languages show as code. No check reads diagrams in v0.
- **Viewing:** the source stays plain nested bullets, with no HTML. A renderer turns a tree into a page where every level below the top starts collapsed, and writes it beside the root file as `<id>.tree/<id>.html`. Git ignores that page, so only the Markdown is reviewed. Collapsing lives in the renderer, not the source, so the tree's diff stays readable prose.

### Files

```
review-agent.tree/
  review-agent.md
  review-output/
    review-output.md
```

- **Root file:** `<id>.tree/<id>.md` holds the root and the top levels. Small trees never need another file.
- **Promoting a subtree:** when a file passes its size budget, its largest subtree moves to `<id>/<id>.md`, in a directory beside that file named for the node's ID. A node needs an ID to be promoted.
- **The node stays put:** its own text remains in the parent file, so skimming the parent still reads normally. Its children are replaced by one line linking to the new file: `- More: [review-output](review-output/review-output.md)`. `More:` lines don't count toward sizes.
- **Promoted files:** start with an H1 title for orientation, then the node's children as top-level bullets.
- **Directories mirror the tree:** each directory holds one node's file plus directories for that node's own promoted descendants. Nothing else goes inside a `.tree` directory, apart from the rendered page.
- **Unique names:** IDs are global, so every file name is unique across the repo. Renaming an ID renames its directory and file.

## Multiple trees

Each independent concept gets its own tree, so a repo will usually have several.

A single repo-wide tree would force one root to summarize unrelated things, and its top level would turn into a table of contents instead of a design. IDs are global, so links work the same within a tree and across trees. One big tree would add nothing for linking.

- **Split a tree** when its top-level bullets cover things a reader would never need together.
- **Merge trees** when they link into each other heavily, or when neither top level makes sense without the other.
- **Link instead of repeating:** a tree can point at another tree's root (`[[review-agent]]`) instead of re-explaining it.
- **Index:** tooling can generate a list of all trees with their root sentences. Nobody maintains it by hand.

## Changing a tree

Structural changes and content changes go in separate commits, with the structural commit first.

- **Structural commit:** moves nodes, adds or removes grouping nodes, nests or flattens, promotes or merges files, and rewrites summaries to fit. It must not add, remove or change any claim. IDs move with their nodes. Prefix the message with `tree(structure):` so reviewers only have to check that meaning was preserved.
- **Content commit:** adds, removes or changes claims, usually in the same commit as the code change it describes. It doesn't move existing nodes.
- **Intermediate commits may break size rules.** A split can land before the content that justifies it. Only the PR's last commit has to pass checks.
- **Edits by people** follow the same rules. When a person's edit breaks one, such as a view over its size, the next agent change to the tree fixes it.

## Checks

Objective breakage fails CI. Sizes only warn until they're far off, and judgment calls belong to the review agent. CI checks only the PR's last commit.

| Check | Kind | Run by |
| --- | --- | --- |
| Every link resolves, including More: links to files | Hard | CI |
| IDs are unique across the repo | Hard | CI |
| Files parse as a tree, hold only Markdown and are named for their node's ID | Hard | CI |
| Node text, view size, child count, file size | Soft: warn at target, fail at 1.5× | CI |
| Nested subtree under 60 words, promoted file under 500 | Warn only | CI |
| Parent doesn't contradict or overclaim | Judgment | Review agent |
| Priority order followed | Judgment | Review agent |
| Structural commits change no claims | Judgment | Review agent |

One CLI, `scripts/trees.py` in this skill's folder, provides these checks plus the lookups agents need instead of guessing: `check` (the CI checks above), `stats` (sizes per node), `links-to <id>` (inbound links) and `render` (the page).

## Example

This sketch shows the shape of a tree for the review agent workflow. The content is placeholder, not the real design.

```markdown
# Review agent {#review-agent}

Every PR gets an automated first-pass review, posted as inline comments, before a human looks.

- Runs as a GitHub Action when a PR is opened or updated {#review-trigger}
  - Skips drafts and PRs that only change docs
  - Why: reviewing every push was noisy and expensive
  - Rejected: a nightly batch, because feedback arrived after the author moved on
- Builds context from the diff plus the design trees it touches {#review-context}
  - Finds the trees a diff touches from each tree's root sentence
  - Why: trees state intent, so the agent can flag code that drifts from it
- Posts findings as inline comments, deduplicated across runs
  - Each finding has a stable fingerprint, so reruns update comments instead of reposting
    - Why: without it, every push stacked duplicate comments
  - Rejected: one summary comment, because authors missed findings with no line anchor
  - Uses the same context as the review itself, see [[review-context]]
```

The root view is about 50 words, so a reader gets the whole pipeline at a glance. The third level is only there to show the syntax: at this size the flatten rule would keep it at two levels.

## Open questions

- **Numbers:** do 40 / 7 / 150 / 60 and the file budgets of 1,500 / 500 hold up? Tune after two or three real trees.
- **Drift detection (not v0):** trees go stale like any other docs, and v0 doesn't try to solve that. A review agent could match each diff against the trees' root sentences, and per-tree path globs would make the match deterministic.
- **Existing docs:** do READMEs and ADRs link into trees, get absorbed into them, or stay as they are?
