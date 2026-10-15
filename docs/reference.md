# Reference

## Commands

Each command syncs the current folder, or `--dir <folder>`, and prints what changed. The folder can also hold several repos without being one itself, so sessions started there get the rules too.

| Command | Does |
|---|---|
| *(none)* | Resyncs every pack at its pinned ref |
| `add <id> <git-url> [--path P] [--ref R] [--when W]` | Installs a pack from git as an import pack at `context-packs/<id>/pack.md`, pinned to the origin's latest commit or to `--ref` |
| `add <id> <folder> [--path P] [--when W]` | Installs a pack read from a folder on disk, such as docs kept elsewhere in the repo, or a pack beside it |
| `remove <id>` | Uninstalls a pack, deleting its import pack |
| `update [id…]` | Moves packs to their latest version |
| `update <id> --ref R` | Pins one pack to a tag or commit |
| `list` | Lists each import pack, where its pack comes from, and its pin |

A pack's id is its import pack's folder under `context-packs/`, such as `core` or `server/database`. Moving the folder changes the id.

## The context-packs folder

`context-packs/` holds every pack a repo has: its own, and an import pack for each pack from elsewhere. The sync renders it into one block of your instruction file, and writes into `context-packs/gen/`, which you never edit. Each pack whose rules or table are inlined sits between `<!-- context-packs:pack <id> -->` and `<!-- context-packs:pack-end <id> -->`, so people reading the file can see where it starts and ends. The sync doesn't read those comments, so they hold nothing to change.

```text
context-packs/
├── pack.md             # your rules, inlined into AGENTS.md
├── deploys.md          # your doc, in the Context table
├── core/pack.md        # an import pack
├── server/
│   ├── pack.md         # your nested pack, with a when
│   └── database/
│       └── pack.md     # an import pack, rendered inside server
└── gen/                # generated
```

Your own docs and nested packs are listed where they are, so editing a doc needs no resync. Changing `pack.md` or a `when:` line, or adding a doc, does.

## Installing from git

```bash
npx context-packs add <id> <git-url> --path <folder>
```

- `<id>` is the folder in `context-packs/` to put the pack at, such as `team-rules`.
- `<git-url>` is the repo holding the pack, as you'd pass it to `git clone`.
- `<folder>` is the pack's folder in that repo, such as `context`. Leave out `--path` if the pack is the whole repo.

That writes an import pack, `context-packs/<id>/pack.md`, which says where the pack comes from and pins it to the origin's latest commit, or to `--ref <tag or commit>`:

```markdown
---
from: https://github.com/acme/auth-service.git
path: agent-pack
ref: e60c2aac61c0e51fd90cf1406318dd785884bb19
---
```

Then it renders the pack into the block, and copies its docs into `context-packs/gen/<id>/`. Origins are fetched with your own git credentials, so private repos work.

## Installing a folder on disk

```bash
npx context-packs add <id> <folder>
```

That writes an import pack whose `from` is a path, relative to the repo, with no `ref`:

```markdown
---
from: docs/agents/project
---
```

The folder is read from your working tree, so it has no pin and `update` leaves it alone. Its table points at the docs where they are, and only the indexes of packs nested in it are generated, into `context-packs/gen/<id>/`. Use it for docs you keep somewhere else in the repo, or [a pack beside the repo](writing-packs.md#trying-a-pack-before-pushing-it). A folder that holds `context-packs/`, or sits inside it, stops the sync, since its packs would render twice.

## Already have an `AGENTS.md` or `CLAUDE.md`?

Keep it. The first run prints two marker lines. Paste them wherever the packs should go, then run it again. If you have both files, paste them into the one that should hold the packs. The packs are synced in at that spot, and the rest of the file stays yours: no sync ever changes it. From then on, the file holding the block is the one synced.

The sync leaves your other instruction file alone. If you keep a separate `CLAUDE.md` while the packs are in `AGENTS.md`, make sure Claude Code reads them, for example with an `@AGENTS.md` line in `CLAUDE.md`. With neither file, the sync creates `AGENTS.md` and links `CLAUDE.md` to it, so every agent reads the same rules.

## Pinning

`--ref` takes a tag or a commit, never a branch, since a branch moves. `update` moves a pack pinned to a commit to the tip of the default branch, and one pinned to a release tag (a prefix and dot-separated numbers, such as `v1.2.0` or `acme-v3`) to the newest release with the same prefix, skipping pre-releases. Other tags stay put. A pack in a folder on disk, such as `.` or `../agent-rules`, isn't pinned.

The commands manage the import packs in `context-packs/`. An import pack inside a pack from elsewhere is that pack's to change: one in a pack from git moves with its holder's pin, and one in a folder on disk is edited there.

## Edits stay upstream

The block ends with a hash of its text and the files under `context-packs/gen/`. If either was edited in the repo, the sync stops and says what to fix: change the pack in its origin, then `update`.

## Upgrading from 0.6

0.7 keeps packs in `context-packs/` and writes one block, where 0.6 kept them in `docs/agents/` with a block for each. A 0.6 file stops the sync and prints the two lines to use instead. To move a repo over:

1. Replace everything from the first `<!-- context-packs:start` line to the last `<!-- context-packs:end` line with the two lines it prints.
2. Move each import pack, such as `docs/agents/core/`, to `context-packs/core/`, and delete `docs/agents/generated/`.
3. Move the repo's own docs into `context-packs/`, or `add` their folder where it is.
4. Run `npx context-packs`.
