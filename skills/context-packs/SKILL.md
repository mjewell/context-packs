---
name: context-packs
description: Sync context packs, which are shared agent rules and docs kept in other git repos, into a repo's AGENTS.md, and add, remove, update or pick nested packs for them. Use when asked to update a repo's shared rules or context packs, install or remove a pack, or change which of a pack's optional nested packs a repo has.
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
   - **Install a pack:** `add <name> <git URL> [--path <folder in the repo>] [--ref <tag or commit>] [--docs a,b]`. Ask for the name if the user didn't give one. Without `--ref` the pack follows the origin's default branch. Any folder in a pack that holds a `pack.md` can be installed on its own, but not alongside a pack from the same origin whose folder holds it or sits inside it.
   - **Remove a pack:** `remove <name>`.
   - **Take the latest:** `update`, or `update <name>…` for some packs. A pack pinned to a commit moves to the default branch's tip, and one pinned to a release tag to the newest release with the same prefix. `update <name> --ref <tag or commit>` pins one pack somewhere specific.
   - **Change nested packs:** run `list`, then `docs <name> a,b`, passing every nested pack the repo picks, by its path in the pack such as `typescript/react` (`''` for none). Picking one installs the packs above it, so pass only the deepest ones wanted. In `list`, each pack's line is `name  origin  path @ ref`, followed by its nested packs as an indented tree: `[x] path: when` for an installed one, `[ ] path: when` for an optional one that isn't, and `(needed by …)` for an optional one installed because a pack inside it was picked.
   - **Add or drop one of the repo's own context docs:** a pack in the repo itself (`from=.` in its marker) reads its docs from its folder, so add or delete the doc there, give a new one a `when:` line in its front matter, and resync with no command.
   - **Resync without changing anything:** no command.
5. If `AGENTS.md` exists without context-packs blocks, the tool stops and prints two lines. Paste them after the file's intro and before its project-specific sections, then run the command again.
6. After an `update`, check the folder containing the repo. If it isn't a git repo and its `AGENTS.md` has a `<!-- context-packs:start header -->` line, it's a synced workspace: run `update` on it too, with `--dir` set to that folder. Workspace sessions read its copy, so it lags otherwise.
7. Report what changed in the repo, from the same `git status` as step 3, and whether the workspace was updated. Leave it uncommitted for the user.
