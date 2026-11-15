# Plan: review in phases, with thread replies

The review action becomes three jobs: find, match and post. Agents read the change through a git server that runs fixed git commands. Findings are paired with pack-review's earlier threads by their text alone, so no comment can change what the review finds or which thread a finding lands in. A script posts everything as one GitHub review: new threads for new findings, and replies only where there's something to say.

This file holds the decisions and the build order while the work lands. Each step adds its reasons to [review.md](../../context-packs/project/review.md) as it lands, and this file is deleted after the last step.

## Goal

- Comments can't change what the review finds, or which thread a finding is paired with.
- Agents ask for what they need through tools, instead of getting files written up front.
- Each finding has one thread. Running the review again doesn't repeat it, so a re-run stays quiet unless something changed.

The review doesn't say whether a thread is resolved. A thread that gets no finding on a later run is most likely fixed, and the author decides that and resolves it.

## Jobs

| Job | Reads comments | Token | Agent | Output |
|---|---|---|---|---|
| 1. find | no | `contents: read` | yes | findings, and the changed paths no agent read |
| 2. match | in its second call only, filtered | `pull-requests: read` | two calls, both with no tools | pairs of a finding and a pack-review thread, and optional commentary per finding |
| 3. post | no | `pull-requests: write` | no | one review, and the summary comment |

Each job's `permissions` are set in the workflow, so GitHub enforces them, not the agent's tools. Results pass between jobs as artifacts.

### 1. find

The `pack-findings` skill, as today. Its subagents each check one unit of the packs, and it merges their answers into findings. The agent reads the change through the git server and never sees a comment.

### 2. match

A script reads pack-review's threads on the PR through `trust.py`, open and resolved. Each thread's first comment is pack-review's, and holds the finding it was opened for as JSON.

Then two agent calls, each with no tools:

1. **Pair.** It gets this run's findings and the findings the threads were opened for, and nothing else. It answers which new finding continues which thread. A finding continues at most one thread. A thread with no finding gets nothing. No comment reaches this call, so none can bias the pairing.
2. **Comment.** For each paired finding, it gets the thread's comments as `trust.py` filters them: the text of people with write access and of pack-review, and only an id for anyone else. It answers commentary for a finding only when there's something to say about it, such as a teammate saying the deviation is deliberate. It sees pack-review's earlier replies, so it doesn't repeat them.

### 3. post

A script, with no agent. It checks that every finding is the one job 1 returned, that each pairing names a pack-review thread on this PR, and that each finding is paired at most once. Then it posts one review:

| Finding | Thread | Posts |
|---|---|---|
| not paired | – | a new thread on its first spot in the diff, holding the finding as JSON |
| not paired, no spot in the diff | – | nothing on the diff, since a review comment needs a line in it |
| paired, with commentary | open or resolved | a reply with the commentary |
| paired, no commentary | open | nothing |
| paired, no commentary | resolved | a reply saying it's still found at `def5678` |
| – | thread with no finding | nothing |

The summary comment keeps every finding as JSON, as today, with each one's thread and commentary, for the local `pack-review`.

The workflow's token can't resolve threads, and most likely can't unresolve them, so a reply is how a resolved thread hears it's still found.

## trust.py

A module, used by job 2's script, that reads one PR's threads and applies who may be read.

- A comment comes back as `{id, author, at, text}` only when its author has write, maintain or admin access now, from GitHub's permission API, cached for the run. pack-review's own comments count: the token's identity wrote them, and they end with the marker.
- Other comments come back as `{id, hidden: <reason>}`, without the login, which is text the author chose. Other bots' comments, and comments a maintainer minimized, are hidden the same way.
- `text` is GitHub's `bodyText`, so GitHub's renderer decides what's hidden, such as HTML comments. Then `sanitize.py` removes invisible characters and redacts secrets.
- It reads every page.

GitHub's lockdown mode doesn't fit: it does nothing on private repos, filters only `issue_read` comments, doesn't strip hidden content, and GitHub calls it best effort.

## Decisions this changes in review.md

- **"CI posts a summary, and no comments on the diff."** Threads come back. The reasons it gave are now covered: `trust.py` filters whose comments are read, and the post script checks which threads are written to. Resolving is still out of reach, so the author resolves.
- **"claude-code-action runs the agent, and the agent has no way to the PR."** Still true. Job 2's agents get the threads from its script and have no tools.
- **The diff and log as files.** Replaced by the git server, so the agent picks what to read.

## Steps

Each step leaves a working review, is written test-first, and adds its reasons to `review.md`.

- [x] 1. The git server, wired into today's single job through `args.py`. `diff.patch` and `log.txt` are dropped, and the summary lists the diffs no agent read.
- [x] 2. Split the workflow into find and post jobs, with the findings passed as an artifact.
- [x] 3. `trust.py`, with tests on GitHub-shaped API answers.
- [x] 4. The match job's pairing, with each finding's thread going into the summary only.
- [ ] 5. The match job's commentary, going into the summary only.
- [ ] 6. Posting the review: new threads, and replies as the table above says.

## Out of scope

- Saying whether a thread is resolved.
- Replying in threads people opened. Only pack-review's own threads get replies.
- The local `pack-review` keeps its fixed `gh` command.

## Open questions

- How commentary is shown in a reply. A code block shows every character, and a link, image or `@mention` in it does nothing. A quote block reads better, but renders Markdown, so commentary could mention people or hide text.
