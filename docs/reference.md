# Reference

## Commands

Each command syncs the current folder, or `--dir <folder>`, and prints what changed. The folder can also hold several repos without being one itself, so sessions started there get the rules too.

| Command | Does |
|---|---|
| *(none)* | Resyncs every pack at its pinned ref |
| `add <name> <git-url> [--path P] [--ref R] [--into F] [--when W]` | Installs a pack from git, pinned to the origin's latest commit or to `--ref`, as an import pack at `F/<name>/pack.md`, with `F` `docs/agents` unless given. Inside a pack of yours, it renders in that pack's block; otherwise it gets its own |
| `add <name> <folder> [--path P]` | Installs a pack read from a folder on disk, such as your own docs or one beside the repo |
| `remove <name>` | Uninstalls a pack, deleting its import pack if it has one |
| `update [name…]` | Moves packs to their latest version |
| `update <name> --ref R` | Pins one pack to a tag or commit |
| `list` | Lists each pack, where it comes from, and its pin, with the import packs inside it under it |

## Installing from git

```bash
npx context-packs add <name> <git-url> --path <folder>
```

- `<name>` is what this repo calls the pack, such as `team-rules`.
- `<git-url>` is the repo holding the pack, as you'd pass it to `git clone`.
- `<folder>` is the pack's folder in that repo, such as `context`. Leave out `--path` if the pack is the whole repo.

That writes an import pack, `docs/agents/<name>/pack.md`, which says where the pack comes from and pins it to the origin's latest commit, or to `--ref <tag or commit>`:

```markdown
---
from: https://github.com/acme/auth-service.git
path: agent-pack
ref: e60c2aac61c0e51fd90cf1406318dd785884bb19
---
```

Then it adds a block for the pack to your instruction file, and copies the pack's docs into `docs/agents/generated/<name>/`. To keep the import pack somewhere else, pass `--into <folder>`. Origins are fetched with your own git credentials, so private repos work.

## Installing a folder on disk

```bash
npx context-packs add <name> <folder>
```

The folder is read from your working tree, so it has no pin. Its block's start marker records the folder, such as `<!-- context-packs:start project path=docs/agents/project -->`. Its table points at the docs where they are, and only its nested packs' indexes are generated, into `docs/agents/generated/<name>/`. Resync after adding a doc or changing a `when:` line or a nested pack's rules.

## Already have an `AGENTS.md` or `CLAUDE.md`?

Keep it. The first run prints two marker lines. Paste them wherever the packs should go, then run it again. If you have both files, paste them into the one that should hold the packs. The packs are synced in at that spot, and the rest of the file stays yours: no sync ever changes it. From then on, the file holding the packs is the one synced.

The sync leaves your other instruction file alone. If you keep a separate `CLAUDE.md` while the packs are in `AGENTS.md`, make sure Claude Code reads them, for example with an `@AGENTS.md` line in `CLAUDE.md`. With neither file, the sync creates `AGENTS.md` and links `CLAUDE.md` to it, so every agent reads the same rules.

## Pinning

`--ref` takes a tag or a commit, never a branch, since a branch moves. `update` moves a pack pinned to a commit to the tip of the default branch, and one pinned to a release tag (a prefix and dot-separated numbers, such as `v1.2.0` or `acme-v3`) to the newest release with the same prefix, skipping pre-releases. Other tags stay put. A pack in a folder on disk, such as `.` or `../agent-rules`, isn't pinned.

## Edits stay upstream

Each block ends with a hash of its text and the files under its `docs/agents/generated/<name>/`. If either was edited in the repo, the sync stops and says what to fix: change the pack in its origin, then `update`.
