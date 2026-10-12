---
name: context-packs
description: Sync context packs, which are shared agent rules and docs kept in other git repos, into a repo's AGENTS.md, add, remove or update them, and write and run a pack's evals. Use when asked to update a repo's shared rules or context packs, install or remove a pack, or test whether a pack's docs get read and change what agents do.
---

# Context packs

Done when the target repo's packs are what the user asked for and synced, any workspace above it is updated too, and the user has seen what changed, left uncommitted.

1. Pick the target: the repo the user names, else the root of the repo this session is working in. Ask when neither settles it. The folder above several repos, which isn't a git repo itself, is synced the same way, as a workspace.
2. Run the tool through npx; it needs `git`, Node 18 or later and Python 3.9 or later:
   ```bash
   npx --yes context-packs --dir <repo> <command>
   ```
3. Note what's already changed in the target, so the report can tell the sync's changes apart:
   ```bash
   git -C <repo> status --short -- AGENTS.md CLAUDE.md docs/agents/packs
   ```
4. Run the command the request calls for. When the tool exits with an error, show the user the message; it says what to fix.
   - **Install a pack:** `add <name> <git URL> [--path <folder in the repo>] [--ref <tag or commit>]`. Ask for the name if the user didn't give one. Without `--ref` the pack follows the origin's default branch. In place of the git URL, a path, such as `../agent-rules`, names a folder on disk. It's read as it is, never pinned, so it takes no `--ref`. Any folder in a pack that holds a `pack.md` can be installed on its own, but not alongside a pack from the same origin whose folder holds it or sits inside it.
   - **Decide when a pack loads, instead of leaving it to its author:** import it into a pack read from a folder on disk, usually the repo's own docs (`from=.`): `add <name> <git URL> [--path <folder>] [--ref <tag or commit>] --into <folder in that pack> [--when <when>]`. It writes an import pack at `<folder>/<name>/pack.md`. With `--when`, the pack gets a row; without it, its rules are pasted into the pack holding it. Afterwards the user owns its `when` and any rules below its front matter, and `update` and `remove` take its name like any pack's. Install a pack that has no folder on disk to hold it into first, such as with `add project . --path docs/agents/project`.
   - **Remove a pack:** `remove <name>`.
   - **Take the latest:** `update`, or `update <name>…` for some packs. A pack pinned to a commit moves to the default branch's tip, and one pinned to a release tag to the newest release with the same prefix. `update <name> --ref <tag or commit>` pins one pack somewhere specific.
   - **Add or drop one of the repo's own context docs:** a pack in the repo itself (`from=.` in its marker) reads its docs from its folder, so add or delete the doc there, give a new one a `when:` line in its front matter, and resync with no command.
   - **Resync without changing anything:** no command.
5. If the repo's `AGENTS.md` or `CLAUDE.md` exists without context-packs blocks, the tool stops, names the file, and prints two lines. When it names both files, ask the user which should hold the packs. Paste the lines into that file, after its intro and before its project-specific sections, then run the command again.
6. After an `update`, check the folder containing the repo. If it isn't a git repo and its `AGENTS.md` or `CLAUDE.md` has a `<!-- context-packs:start header -->` line, it's a synced workspace: run `update` on it too, with `--dir` set to that folder. Workspace sessions read its copy, so it lags otherwise.
7. Report what changed in the repo, from the same `git status` as step 3, and whether the workspace was updated. Leave it uncommitted for the user.

## Evals

Done when the evals the user asked for are written or run, and the user has seen each score and the folder holding the reports and transcripts.

- **Where tests go:** a doc's tests sit in a `.evals` folder beside it, under a folder named after the doc: `<pack>/.evals/<doc>/` for `<pack>/<doc>.md`. A nested pack's docs have their tests in its own `.evals`. The sync skips `.evals`.
- **Triggers** check that agents read the doc when they should. Write them in `.evals/<doc>/triggers.md`, exactly this shape, since anything else stops the eval:
  ```markdown
  ## Reads

  - A prompt that should make an agent read the doc
  - A prompt over more than one line,
    with each further line indented under its item

  ## Skips

  - A prompt that shouldn't
  ```
  Optional front matter goes to every prompt's run. Make Skips near misses, prompts close to the doc's `when` that still shouldn't match it, since those are what catch a `when` that's too broad.
- **Cases** check that the doc changes what agents do. Each is a folder in `.evals/<doc>/` in `claude plugin eval`'s format: a `prompt.md` with front matter such as `max_turns` and `allowed_tools`, and graders in `graders/*.md`. A case should hinge on something only that doc says: when the repo's other instructions also say it, the case scores the same without the doc and measures nothing.
- **Run them** from a repo with the pack installed, which needs Claude Code: `npx --yes context-packs --dir <repo> eval <name> [doc] [-- <claude plugin eval options>]`, with `doc` as its path in the pack without `.md`. Each trigger runs with the doc; each case runs without the doc, then with it, and a positive change means the doc helps. Every run spends the user's Claude usage: `eval` lists the cases before it starts, and each runs three times by default, on Haiku unless the options name a model with `--model`, 4 cases at a time unless `-j <n>` says otherwise. Unless the user said how much to run, offer `-- --runs 1` for a quick check, and a larger model when the user wants to know how the model their sessions use behaves. To test a pack being written, install it into an empty folder from its working tree, by a path such as `../agent-rules`, then run `eval` there.
