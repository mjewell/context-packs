# Plan: review in phases, with thread replies

The review action becomes four jobs. Only one of them reads PR comments, and nothing it reads can change a finding or a thread's status. Agents read the change and the PR through two small MCP servers that enforce what they may see. A script posts everything, as one GitHub review that replies in pack-review's own open threads and starts new ones.

This file holds the decisions and the build order while the work lands. Each step adds its reasons to [review.md](../../context-packs/project/review.md) as it lands, and this file is deleted after step 5.

## Goal

- Comments can't change what the review finds, or whether a thread reads as resolved.
- Agents ask for what they need through tools, instead of getting files written up front.
- The author hears whether each open pack-review thread is still flagged or looks resolved, instead of getting new threads on every push.

## Jobs

| Job | Reads comments | Token | Agent | Output |
|---|---|---|---|---|
| 1. find | no | `contents: read` | yes | findings, and the changed paths each unit didn't read |
| 2. match | no | `pull-requests: read`, for its script only | yes, with no tools | pairs of a finding and a pack-review thread |
| 3. discuss | yes, through the GitHub server | `pull-requests: read` | yes | a verdict and note per pack-review thread, notes on findings |
| 4. post | no | `pull-requests: write` | no | one review, and the summary comment |

Each job's `permissions` are set in the workflow, so GitHub enforces them, not our `claude_args`. Results pass between jobs as artifacts. Jobs 1 and 3 can run at the same time. Job 3 runs only when pack-review has open threads.

### 1. find

The same `pack-findings` run as today, with the same tools, plus the git server. It never sees a comment. `diff.patch` and `log.txt` go away: the agent reads the diff path by path, so it can skip a lock file. The transcript shows which paths each unit read, and the summary's JSON lists the ones it skipped. A skipped path doesn't make the review partial, since skipping a lock file is often right.

### 2. match

A script fetches the findings that pack-review's open threads were opened for, from those threads' first comments. pack-review wrote them, and the script reads no other comment. An agent pairs them with job 1's findings. A finding may continue several threads, and a thread may take several findings. It never sees a comment, so a comment can't make it leave out a match.

### 3. discuss

An agent with the GitHub server and the checkout. For each open pack-review thread, it reads the thread and the code at head, and answers `resolved` or `unresolved` with a note. For findings, it answers notes as `{finding, comment, quote, relation}`, where `relation` is one of a fixed set, such as `explains`, `disputes` or `says-fixed`. The post script rejects a quote that isn't word for word in that comment's text as the server served it.

### 4. post

A script, with no agent. It checks that every finding from job 1 is unchanged, and that every thread id in the plan is a pack-review thread on this PR. Then it posts one review:

- A thread job 2 matched gets a reply with a fixed status line, and job 3's note under it.
- A finding job 2 matched to no thread starts a new thread on its first spot. A finding whose spots are all outside the diff goes only in the summary, since a review comment needs a line in the diff.
- The summary comment keeps every finding as JSON, as today, for the local `pack-review`.

A thread's status comes from both signals:

| Job 3 says | Job 2 matched a finding | Status line |
|---|---|---|
| resolved | no | Looks resolved at `abc1234` |
| resolved | yes | Still flagged at `abc1234`: the review found it again |
| unresolved | no | Still open at `abc1234` |
| unresolved | yes | Still open at `abc1234` |

"Looks resolved" needs job 2, which never saw a comment. A comment that pushes job 3 toward `unresolved` only keeps a thread open. The workflow's token can't resolve threads, so the author does that.

## The git server

A Python stdio MCP server using only the standard library, for job 1.

| Tool | Returns |
|---|---|
| `changed()` | every changed path, with its size in lines |
| `diff(path)` | the diff of one path, from the merge base to head, paged |
| `log(path, limit)` | commits that touched a path, with their messages |
| `show(commit)` | one commit's message and diff |
| `blame(path, start, end)` | the commit behind each line at head |
| `file(rev, path)` | a file at a revision, paged |

The agent's text never reaches git as an option. That's why this is safe when an allowed shell `git` wasn't: `git log --output=<file>` wrote any file, and git takes any unique prefix of `--output`.

- Each tool runs one fixed `argv`, with no shell.
- Revisions are checked with `git rev-parse --verify --end-of-options <rev>^{commit}`, and only the resolved hash is passed on.
- Paths go after `--`, must be relative, and can't contain `..`.
- Every call adds `--no-ext-diff --no-textconv`. No tool reads `.git/config`, where claude-code-action keeps its token.
- Output is paged, with a cap on lines.

## The GitHub server

A Python stdio MCP server using only the standard library, for job 3. It's tied to one PR, read from the job's environment when it starts, and no tool takes a repo or number. It has no write tools.

| Tool | Returns |
|---|---|
| `pr()` | title, description, author, head, base |
| `threads()` | every review thread: id, path, line, whether pack-review opened it, open or resolved |
| `thread(id)` | that thread's comments |
| `comments()` | PR-level comments |
| `reviews()` | review bodies |

- A comment comes back as `{id, author, at, text}` only when its author has write, maintain or admin access now, from GitHub's permission API, cached for the run. pack-review's own comments count: the token's identity wrote them, and they end with the marker.
- Other comments come back as `{id, hidden: "author lacks write access"}`, without the login, which is text the author chose. Other bots' comments, and comments a maintainer minimized, are hidden the same way.
- `text` is GitHub's `bodyText`, so GitHub's renderer decides what's hidden, such as HTML comments. Then `sanitize.py` removes invisible characters and redacts secrets.
- It reads every page.

Job 2's script uses the same module to fetch pack-review's threads, so the trust rule has one home. GitHub's lockdown mode doesn't fit: it does nothing on private repos, filters only `issue_read` comments, doesn't strip hidden content, and GitHub calls it best effort.

## Decisions this changes in review.md

- **"CI posts a summary, and no comments on the diff."** Threads come back. The reasons it gave are now covered: the GitHub server filters whose comments are read, and the post script checks which threads are written to. Resolving is still out of reach, so pack-review replies and the author resolves.
- **"claude-code-action runs the agent, and the agent has no way to the PR."** Still true for jobs 1 and 2. Job 3 reads the PR, through the GitHub server only.
- **The diff and log as files.** Replaced by the git server, so the agent picks what to read.

## Steps

Each step leaves a working review, is written test-first, and adds its reasons to `review.md`.

- [ ] 1. The git server, wired into today's single job through `args.py`. `diff.patch` and `log.txt` are dropped, and the summary lists skipped paths.
- [ ] 2. Split the workflow into jobs, starting with find and then post, with the findings passed as an artifact.
- [ ] 3. The GitHub server and its trust module, with tests on recorded API answers.
- [ ] 4. The discuss job, with its notes on findings going into the summary only.
- [ ] 5. The match job, and posting the review: thread replies, new threads and the status table.

## Out of scope

- Replying in threads people opened. Only pack-review's own threads get replies.
- The local `pack-review` keeps its fixed `gh` command. A local session has other GitHub tools, so this server couldn't stop it reading around the filter.

## Open questions

- How job 3's note is shown under the status line. A code block shows every character, and a link, image or `@mention` in it does nothing. A quote block reads better, but renders Markdown, so a note could mention people or hide text.
