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
| `check` | Exits 1, naming what's stale, if a sync would change anything, and writes nothing |
| `eval [doc…] [--pack F] [--runs N] [--model M]` | Runs each pack's eval prompts, checking that an agent reads each doc when it should, and only then |

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

For a folder in the repo, such as docs you'd rather keep where they are, that writes an import pack holding just the folder's path, relative to the repo:

```markdown
---
path: docs/agents/project
---
```

For a folder outside the repo, such as a checkout beside it, `from` names that folder and `path` the folder in it, the same shape as a pack from git without its `ref`:

```markdown
---
from: ../agent-rules
path: context
---
```

Either way the folder is read from your working tree, so it has no pin and `update` leaves it alone. A `path` can't leave the repo it's in: name the other repo in `from` instead. Its table points at the docs where they are, and only the indexes of packs nested in it are generated, into `context-packs/gen/<id>/`. Use it for docs you keep somewhere else in the repo, or [a pack beside the repo](writing-packs.md#trying-a-pack-before-pushing-it). A folder that holds `context-packs/`, or sits inside it, stops the sync, since its packs would render twice.

## Already have an `AGENTS.md` or `CLAUDE.md`?

Keep it. The first run prints two marker lines. Paste them wherever the packs should go, then run it again. If you have both files, paste them into the one that should hold the packs. The packs are synced in at that spot, and the rest of the file stays yours: no sync ever changes it. From then on, the file holding the block is the one synced.

The sync leaves your other instruction file alone. If you keep a separate `CLAUDE.md` while the packs are in `AGENTS.md`, make sure Claude Code reads them, for example with an `@AGENTS.md` line in `CLAUDE.md`. With neither file, the sync creates `AGENTS.md` and links `CLAUDE.md` to it, so every agent reads the same rules.

## Pinning

`--ref` takes a tag or a commit, never a branch, since a branch moves. `update` moves a pack pinned to a commit to the tip of the default branch, and leaves one pinned to a tag where it is: move it with `update <id> --ref <tag>`. It prints a line for each pack it covers, such as `core: 9faa48e → 1a2b3c4`, `typescript: 9faa48e (up to date)` or `frontend: v1.4.0 (tag)`. A pack in a folder on disk, such as `.` or `../agent-rules`, isn't pinned.

The commands manage the import packs in `context-packs/`. An import pack inside a pack from elsewhere is that pack's to change: one in a pack from git moves with its holder's pin, and one in a folder on disk is edited there.

## Edits stay upstream

The block ends with a hash of its text and the files under `context-packs/gen/`. If either was edited in the repo, the sync stops and says what to fix: change the pack in its origin, then `update`.

## Checking in CI

`check` renders every pack the way a sync would, and fails if `AGENTS.md` or a file in `context-packs/gen/` differs, such as after a `when:` line or a pinned `ref` changed without a resync, or after synced content was edited in place:

```yaml
- uses: actions/checkout@v4
- run: npx --yes context-packs check
```

It fetches packs from git at their pins, as a sync does, so a repo installing packs from a private repo needs git credentials that can read it.

## Testing when each doc gets read

A row only helps if an agent reads its doc when the work matches, and leaves it alone otherwise. To check, write prompts for a doc in its pack's `.evals/` folder, at the pack's root, in a file named by the doc's path in the pack, such as `.evals/testing.md`:

````markdown
## Reads

- The date parser returns the wrong month for ISO strings. Fix it.
- CI failed with this:

  ```
  FAIL src/parse.test.ts > parses ISO dates
  ```

## Skips

- Explain how parseIsoDate works.
````

Each `- ` item is a prompt, and lines indented under it continue it. `npx context-packs eval` runs each prompt as a Claude Code session (`claude -p`), and checks whether the session read the doc: it should for a prompt under `## Reads`, and shouldn't under `## Skips`.

A pack's prompts run with that pack installed alone, plus everything inside it, since a pack meant to be installed can't know what it will sit beside. `context-packs/` is the pack at the top, and everything the repo installs sits inside it, so prompts in `context-packs/.evals/` run with the whole repo. That's where to test your own docs, and to check how a pack you install behaves among your rules: `context-packs/.evals/core/testing.md` tests the `core` pack's `testing.md` in your repo. To test some of your own docs alone, move them into a folder with its own `.evals/`, and add it back with an import pack holding its `path`.

`eval` runs the prompts of `context-packs/` and of every pack inside it read in place, and `eval --pack <folder>` runs one pack's, whether the repo installs it or not, as for a repo of packs written for others. Name docs as it prints them to run only theirs, and pass `--runs 3` to see whether a result holds up: a prompt passes only if every run does.

The sessions for `context-packs/` run in a copy of the repo, and for any other pack in an empty folder with just that pack installed. If the prompts are about code that isn't there, put a folder for them to run in at `.evals/fixture/`, such as a small fake project: its copy gets the pack installed and synced instead, with a folder read in place named by its absolute path so its rows still point here. To share a fixture between packs, link each `.evals/fixture` to it. A fixture can't have a `context-packs/` of its own.

Every copy sits outside your folders, without `.git`, `node_modules` or `.evals`, and loads only its own `CLAUDE.md`. Sessions get only the tools that look (`Read`, `Glob` and `Grep`), no MCP servers, and up to 8 turns, and each ends as soon as it reads its doc, since that settles its prompt either way, or where it runs out of turns. A prompt that fails lists the docs its session read. A session that errors instead, such as one without a login or on a model you can't use, settles nothing: its prompt shows `!` and claude's error, and `eval` exits 1. Sessions use your Claude Code login and cost tokens, about 20–30k each, and run on Sonnet unless you pass `--model`. Results depend on the model, and a prompt that passes only on a larger one points at a `when` worth making plainer.

Prompts close to a row's `when` that shouldn't match it, or that match only through a clause that's easy to miss, are the ones worth writing.

## Upgrading from 0.6

0.7 keeps packs in `context-packs/` and writes one block, where 0.6 kept them in `docs/agents/` with a block for each. A 0.6 file stops the sync and prints the two lines to use instead. To move a repo over:

1. Replace everything from the first `<!-- context-packs:start` line to the last `<!-- context-packs:end` line with the two lines it prints.
2. Move each import pack, such as `docs/agents/core/`, to `context-packs/core/`, and delete `docs/agents/generated/`.
3. Move the repo's own docs into `context-packs/`, or `add` their folder where it is.
4. Run `npx context-packs`.
