# Spec trees, v0

Nov 18, 2026 · @Michael Jewell

## Purpose

A spec tree is a nested outline of how one part of a system works and why, kept small enough at every level to skim. You read the top level for the overall shape and expand only the branches you care about, down to the finest details of behavior and decisions at the leaves.

Spec trees exist so a person can keep up with code that agents write. Agents update the tree in the same PR as the code, so the tree's diff is a readable changelog of design changes.

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
- **Word count:** whitespace-separated words after removing markup. Labels, IDs, link slugs, code paths and diagrams don't count. A link's display text counts.

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

**Term rule.** A term is a name the project coined, or an ordinary word used in a narrower sense, such as "view" in this spec. Each node that uses a term links its first use to the node that defines it, as in `[[findings|finding]]`. Only the defining node leaves its own term unlinked. The tree's subject, the term its root names, stays unlinked too, since a link to the root only jumps to the top of the page. A term the tree defines nowhere gets defined in the highest node that uses it.

- **Why:** a reader can reach any node without reading what's above or before it. They skim, pick a branch, or arrive by a link. A link costs a reader who already knows the term almost nothing, since the page shows links quietly.
- **Rejected:** linking only where the definition isn't on the reader's way down to the node. Which nodes a reader has read depends on how they read, so no rule about position holds.

## Format

A tree is one Markdown file of nested bullets, named `<id>.tree.md` and kept next to the code it describes.

```markdown
# Review agent {#review-agent}

Every PR gets an automated first-pass review before a human looks.

- Runs as a GitHub Action when a PR is opened or updated {#review-trigger}
  - Why: reviewing every push was noisy and expensive
  - Rejected: a nightly batch, because feedback came too late
- Reads the spec trees for the files it touches, see [[tree-lookup]]
```

- **Root:** an H1 title with the tree's ID, then one sentence on what the tree covers, then the top-level bullets. Front matter is allowed but ignored, and the spec reserves no keys.
- **Nesting:** two-space indent per level.
- **Labels:** a node may start with a label, written exactly `Why:` or `Rejected:`. A node that starts with either word in another form, such as "Rejected, since…", fails `check`, since it shows as plain text instead of a label. Unlabeled nodes say what something is or how it works. Labels let readers and tooling spot decisions. A labeled node is about its parent. `Why:` gives a reason for the parent's claim, and `Rejected:` names an alternative to it.
- **Rejections:** a rejected alternative always gets its own `Rejected:` node, never an inline "rather than" or "instead of", so every rejection shows as a label.
- **Reasons:** a short reason the claim doesn't read without stays inline, as in "…, since a review comment needs a line in the diff". A reason gets its own `Why:` node when it's evidence or history, such as what went wrong before, or when inline it would push the node past its size.
- **One decision per node:** a node may have several `Why:` children when they're separate reasons for the same claim. When they justify different decisions in one node, split it so each decision has its own node.
- **IDs:** `{#slug}` at the end of a node's text. A node has at most one, and only nodes that something links to need one. IDs are unique across the repo and stay with the node when it moves. When a node's meaning changes, rename its ID: every incoming link breaks, and the checks force each one to be revisited.
- **Links:** `[[slug]]` points at a node in any tree in the repo. `[[slug|text]]` shows the text in place of the slug, for a term whose form differs from the ID, such as a plural. The text may hold a code span, as in ``[[doc|`when`]]``. Links target IDs, never positions or files, so moving a node never breaks a link. A link is a jump, not an expansion: expanding a node shows its own children, never a linked node's children. Depth follows parent-child edges only, so cycles through links are harmless.
- **Merges and deletes:** when two nodes merge, the merged node keeps whichever existing ID fits it, or gets a new one when neither does. Merging, deleting or renaming a node means fixing its inbound links in the same commit. `links-to <id>` lists them, and the link check fails on any left over.
- **Diagrams:** a node may hold a diagram as a fenced code block, indented under its text. The diagram belongs to the node and isn't one of its children. Put it on the node whose structure it shows, so expanding that node shows the picture beside the children it describes. Any diagram language works. Mermaid renders on GitHub, and other languages show as code. No check reads diagrams in v0.
- **Viewing:** the source stays plain nested bullets, with no HTML. A renderer turns a tree into a page where every level below the top starts collapsed, and writes it beside the tree's file as `<id>.tree.html`. Git ignores that page, so only the Markdown is reviewed. Collapsing lives in the renderer, not the source, so the tree's diff stays readable prose.

### One file

A tree stays one file however large it grows.

- **Why:** the rendered page does the collapsing, and a diff shows only the lines that changed, whatever the file's size. Splitting a tree across files would add rules without helping anyone reading the page or reviewing a diff.
- **No size cap:** nothing limits how large a tree gets. People decide when a tree should become separate trees (see Multiple trees).
- **Rejected:** promoting large subtrees into their own files, linked from the parent by a `More:` line. It kept raw files small, but nobody reads a tree's raw Markdown except in a diff.

## Multiple trees

Each independent concept gets its own tree, so a repo will usually have several.

A single repo-wide tree would force one root to summarize unrelated things, and its top level would turn into a table of contents instead of a design. IDs are global, so links work the same within a tree and across trees. One big tree would add nothing for linking.

- **Split a tree** when its top-level bullets cover things a reader would never need together.
- **Merge trees** when they link into each other heavily, or when neither top level makes sense without the other.
- **Link instead of repeating:** a tree can point at another tree's root (`[[review-agent]]`) instead of re-explaining it.
- **Index:** tooling can generate a list of all trees with their root sentences. Nobody maintains it by hand.

## Changing a tree

Structural changes and content changes go in separate commits, with the structural commit first.

- **Structural commit:** moves nodes, adds or removes grouping nodes, nests or flattens, and rewrites summaries to fit. It must not add, remove or change any claim. IDs move with their nodes. Prefix the message with `tree(structure):` so reviewers only have to check that meaning was preserved.
- **Content commit:** adds, removes or changes claims, usually in the same commit as the code change it describes. It doesn't move existing nodes.
- **Intermediate commits may break size rules.** A split can land before the content that justifies it. Only the PR's last commit has to pass checks.
- **Edits by people** follow the same rules. When a person's edit breaks one, such as a view over its size, the next agent change to the tree fixes it.

## Checks

Objective breakage fails CI. Sizes only warn until they're far off, and judgment calls belong to the review agent. CI checks only the PR's last commit.

| Check | Kind | Run by |
| --- | --- | --- |
| Every link resolves | Hard | CI |
| IDs are unique across the repo | Hard | CI |
| Each tree file parses as a tree | Hard | CI |
| Labels are written `Why:` or `Rejected:` | Hard | CI |
| Node text, view size, child count | Soft: warn at target, fail at 1.5× | CI |
| Nested subtree of 60 words or fewer | Warn only | CI |
| Parent doesn't contradict or overclaim | Judgment | Review agent |
| Priority order followed | Judgment | Review agent |
| Every rejection has its own `Rejected:` node | Judgment | Review agent |
| Each node links its terms | Judgment | Review agent |
| Structural commits change no claims | Judgment | Review agent |

One CLI, `scripts/trees.ts` in this skill's folder, provides these checks plus the lookups agents need instead of guessing: `check` (the CI checks above), `stats` (sizes per node), `links-to <id>` (inbound links) and `render` (the page).

## Example

This sketch shows the shape of a tree for the review agent workflow. The content is placeholder, not the real design.

```markdown
# Review agent {#review-agent}

Every PR gets an automated first-pass review, posted as inline comments, before a human looks.

- Runs as a GitHub Action when a PR is opened or updated {#review-trigger}
  - Skips drafts and PRs that only change docs
  - Why: reviewing every push was noisy and expensive
  - Rejected: a nightly batch, because feedback arrived after the author moved on
- Builds context from the diff plus the spec trees it touches {#review-context}
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

- **Numbers:** do 40 / 7 / 150 / 60 hold up? Tune after two or three real trees.
- **Drift detection (not v0):** trees go stale like any other docs, and v0 doesn't try to solve that. A review agent could match each diff against the trees' root sentences, and per-tree path globs would make the match deterministic.
- **Diff mode (not v0):** a page that shows how a tree changed between two commits. It marks each added, removed and changed node, and opens the branches above them. It could be rendered for two given commits, or hold every version and let the reader pick two. Matching nodes across versions is the hard part, since only some nodes have IDs and structural commits move them. Wait until a tree has history to try it on.
- **Existing docs:** do READMEs and ADRs link into trees, get absorbed into them, or stay as they are?
