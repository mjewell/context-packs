---
name: context-packs
description: Sync context packs, which are shared agent rules and docs kept in other git repos, into a repo's AGENTS.md, and add, remove or update them. Use when asked to update a repo's shared rules or context packs, or install or remove a pack.
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
   git -C <repo> status --short -- AGENTS.md CLAUDE.md context-packs
   ```
4. Run the command the request calls for. When the tool exits with an error, show the user the message; it says what to fix.
   - **Install a pack:** `add <id> <git URL> [--path <folder in the repo>] [--ref <tag or commit>] [--when <when>]`. The id is the folder under `context-packs/` to put it at, such as `core` or `server/database`; ask for it if the user didn't give one. It writes an import pack at `context-packs/<id>/pack.md`, holding the pack's origin and pin. Without `--ref` the pack follows the origin's default branch. Any folder in a pack that holds a `pack.md` can be installed on its own, but not alongside a pack from the same origin whose folder holds it or sits inside it.
   - **Install docs kept elsewhere in the repo, or a folder beside it:** `add <id> <folder>`, such as `add project docs/agents/project` or `add rules ../agent-rules --path context`. It's read as it is, never pinned, so it takes no `--ref`. A folder in the repo gets an import pack holding just its `path`; one outside it gets `from` too.
   - **Decide when a pack loads, instead of leaving it to its author:** set `when:` in its import pack's front matter and resync, or pass `--when` to `add`. `when: always` inlines its rules into every session; any other `when` gives it a row. The user owns an import pack's `when` and any rules below its front matter.
   - **Group packs, or move one:** move its folder within `context-packs/` and resync; it renders where it now sits, and its id becomes its new folder. To put several packs behind one row of the user's, move their folders into a folder whose `pack.md` has a `when`.
   - **Remove a pack:** `remove <id>`.
   - **Take the latest:** `update`, or `update <id>…` for some packs. A pack pinned to a commit moves to the default branch's tip, and one pinned to a release tag to the newest release with the same prefix. `update <id> --ref <tag or commit>` pins one pack somewhere specific.
   - **Add or drop one of the repo's own context docs:** add or delete the doc in `context-packs/`, give a new one a `when:` line in its front matter, and resync with no command.
   - **Resync without changing anything:** no command.
5. If the repo's `AGENTS.md` or `CLAUDE.md` exists without a context-packs block, the tool stops, names the file, and prints two lines. When it names both files, ask the user which should hold the packs. Paste the lines into that file, after its intro and before its project-specific sections, then run the command again. If it says the file has blocks from an older version, follow the steps it prints, which `docs/reference.md` in mjewell/context-packs also lists under "Upgrading from 0.6", and show the user the result before going on.
6. After an `update`, check the folder containing the repo. If it isn't a git repo and its `AGENTS.md` or `CLAUDE.md` has a `<!-- context-packs:start` line, it's a synced workspace: run `update` on it too, with `--dir` set to that folder. Workspace sessions read its copy, so it lags otherwise.
7. Report what changed in the repo, from the same `git status` as step 3, and whether the workspace was updated. Leave it uncommitted for the user.
