---
name: context-packs
description: Sync context packs, which are shared agent rules and docs kept in other git repos, into a repo's AGENTS.md, and add, remove, update or choose doc sets for them. Use when asked to update a repo's shared rules or context packs, install or remove a pack, or change which of a pack's doc sets a repo has.
---

# Context packs

Done when the target repo's packs are what the user asked for and synced, and the user has seen what changed, left uncommitted.

1. Pick the target: the repo the user names, else the root of the repo this session is working in. Ask when neither settles it. The folder above several repos, which isn't a git repo itself, is synced as a workspace: pass `--workspace` before the command.
2. Find the tool: `bin/context-packs.js` in the repo holding this skill. This skill's folder may be a symlink, so resolve it first:
   ```bash
   node "$(realpath <skill-dir>)/../../bin/context-packs.js" <repo> <command>
   ```
3. Note what's already changed in the target, so the report can tell the sync's changes apart:
   ```bash
   git -C <repo> status --short -- AGENTS.md CLAUDE.md docs/agents/packs
   ```
4. Run the command the request calls for. When the tool exits with an error, show the user the message; it says what to fix.
   - **Install a pack:** `add <name> <git URL> [--path <folder in the repo>] [--ref <tag or commit>] [--docs a,b]`. Ask for the name if the user didn't give one. Without `--ref` the pack follows the origin's default branch.
   - **Remove a pack:** `remove <name>`.
   - **Take the latest:** `update`, or `update <name>…` for some packs. A pack pinned to a commit moves to the default branch's tip, and one pinned to a release tag to the newest release with the same prefix. `update <name> --ref <tag or commit>` pins one pack somewhere specific.
   - **Change doc sets:** run `list`, then `docs <name> a,b`, passing every optional set the pack should have, installed ones included (`''` for none). In `list`, each pack's line is `name  origin  path @ ref`, followed by `[x] set: when` for an installed optional set, `[ ] set: when` for one that isn't, and `[x] set (required): when` for one every repo gets.
   - **Add or drop one of the repo's own context docs:** a pack in the repo itself (`from=.` in its marker) installs every doc set in its folder, so add or delete the doc there, give a new one a `when:` line in its front matter, and resync with no command.
   - **Resync without changing anything:** no command.
5. If `AGENTS.md` exists without context-packs blocks, the tool stops and prints two lines. Paste them after the file's intro and before its project-specific sections, then run the command again.
6. Report what changed, from the same `git status` as step 3. Leave it uncommitted for the user.
