# context-packs

Pull the context your teams write for coding agents into each repo's `AGENTS.md`.

Whoever knows a topic writes its rules and docs once, as a pack: the auth team on sessions and permissions, the frontend team on forms and components. Each repo installs the packs that apply to it, alongside its own docs. The web app takes auth and frontend, and an API service takes auth, backend and database.

Two packs synced into a web app's `AGENTS.md`:

```markdown
<!-- context-packs:start auth path=docs/agents/auth -->
Never log tokens, session IDs or passwords, even at debug level.

## auth context

| When | Read |
|---|---|
| Adding an endpoint, or checking what a user may do | `docs/agents/generated/auth/permissions.md` |
| Reading the signed-in user, or changing sign-in or sign-out | `docs/agents/generated/auth/sessions.md` |
<!-- context-packs:end sha256:3ccb7c0b8f64 -->

<!-- context-packs:start frontend path=docs/agents/frontend -->
Build UI from `@acme/ui` components; don't style raw HTML elements. Every user-facing string goes through `t()`.

## frontend context

| When | Read |
|---|---|
| Adding anything a user can click, type into or focus | `docs/agents/generated/frontend/accessibility.md` |
| Building or changing a form | `docs/agents/generated/frontend/forms.md` |
| Writing or changing React components | `docs/agents/generated/frontend/react.md` |
<!-- context-packs:end sha256:94fffbdf036a -->
```

[The full example](docs/example.md) shows the packs, the commands, and every file they generate.

- **Mix packs from anywhere.** A pack is a folder in any git repo, and each one gets its own block, pinned and updated on its own.
- **You decide how each pack loads.** A pack's author suggests whether its rules load in every session or only when a row matches, and your repo can choose differently for any pack.
- **Keeps what you already have.** Packs sync into the `AGENTS.md` or `CLAUDE.md` you already have, and your own content in it stays. The packs go wherever you put them in the file, and the sync never touches the rest.
- **Docs load only when they apply.** Long docs stay out of every session. `AGENTS.md` gets a table saying when to read each one.
- **Committed, so every session sees it.** Packs are copied in, not linked or loaded by a hook, so clones, CI and cloud agent sessions get them too.
- **Fixed once, at the source.** A pack's owners change it in its repo, and every repo picks up the change with `update` instead of keeping its own copy that drifts.
- **Any agent.** Anything that reads `AGENTS.md` or `CLAUDE.md` works. A repo with neither gets an `AGENTS.md`, with `CLAUDE.md` linked to it for Claude Code.

Run it with `npx context-packs`, or [let your agent run it](#let-your-agent-run-it). It needs `git`, Node 18+ and Python 3.9+; on macOS, the command line tools provide both `git` and Python.

## Write a pack

A pack is a folder in any git repo. `pack.md` holds the rules every session sees, and every other `.md` file is a doc that only gets read when it's relevant. A folder holding a `pack.md` of its own is a nested pack, and a folder without one just groups files:

```text
context/
├── pack.md          # rules pasted into every repo's AGENTS.md
├── testing.md       # a doc
├── git/
│   └── prs.md       # a doc, grouped in a folder
└── typescript/      # a nested pack
    ├── pack.md
    ├── types.md
    └── react/       # a nested pack inside it
        └── pack.md
```

Each doc starts with front matter whose `when` becomes its row in the table:

```markdown
---
when: Writing or changing tests
---
```

A nested pack gets a row too, from the `when` in its `pack.md`, pointing at a generated index that holds its rules and a table of its own docs and nested packs. One whose `when` is `always` is pasted after its parent's rules and table instead, for rules that matter whenever its parent does. Each nested pack is a read an agent makes before reaching the docs inside it, so nest only where a subtree is big and its `when` is sharp, and use plain folders to group the rest. Files other than `.md` files, such as code examples, are copied along with the docs beside them.

A nested pack is installed whenever its parent is. A part only some repos want, such as a language's rules, goes in a pack of its own, in a folder beside its parent's rather than inside it, and those repos install it with `add`.

Any folder with a `pack.md` can also be installed on its own, as its own pack, and it renders the way it would inside its parent. If its `pack.md` has a `when`, its block in `AGENTS.md` is a one-row table pointing at a generated index of its rules, so installing just `typescript` still loads its rules only when a row matches. Without a `when`, or with `when: always`, its rules are pasted into the block.

Keep `pack.md` short, since every session loads it.

Tags are optional. A repo pins to a commit by default, and `update` moves it to the tip of your default branch. Tag releases like `v1.2.0` once you want repos to pin to versions and `update` from one release to the next.

**One repo or many.** A pack can sit beside the code it describes, such as an `agent-pack/` folder in the auth service, or in a repo that several teams share, with a folder for each. Each install is its own pack with its own pin, even when two come from the same repo, so choose based on who owns and releases what. In a shared repo, give each pack's tags its own prefix, such as `frontend-v1.4.0` and `database-v2.0.0`, and `update` moves each pack along its own series.

## Sync a pack from another repo

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

Then it adds a block for the pack to your instruction file, creating `AGENTS.md` if you have none, and copies the pack's docs into `docs/agents/generated/<name>/`. Commit the result. To keep the import pack somewhere else, pass `--into <folder>`.

**Already have an `AGENTS.md` or `CLAUDE.md`?** Keep it. The first run prints two marker lines. Paste them wherever the packs should go, then run it again. If you have both files, paste them into the one that should hold the packs. The packs are synced in at that spot, and the rest of the file stays yours: no sync ever changes it. From then on, the file holding the packs is the one synced.

The sync leaves your other instruction file alone. If you keep a separate `CLAUDE.md` while the packs are in `AGENTS.md`, make sure Claude Code reads them, for example with an `@AGENTS.md` line in `CLAUDE.md`. With neither file, the sync creates `AGENTS.md` and links `CLAUDE.md` to it, so every agent reads the same rules.

Later, `npx context-packs update` moves packs to their latest version, and `npx context-packs` resyncs at the pinned ones. Private repos work, since origins are fetched with your own git credentials.

**Trying a pack before pushing it?** Pass the path of a folder beside the repo in place of the git URL: `npx context-packs add <name> ../agent-rules --path <folder>`. Its block reads that folder as it is on disk, like your own docs, so there's no import pack and no ref to pin, and the table points at the docs where they are. Edits to a doc show up without a resync. Changes to `pack.md` or a `when:` line need one, since those are copied into `AGENTS.md`. It syncs only where that folder exists, so it's for trying a pack out, not for a repo that clones, CI and cloud sessions sync.

## Sync your project's own docs

The same table works for a repo's own docs. Put them in a folder, each with a `when:` line, and install the folder as a pack:

```bash
npx context-packs add <name> <folder>
```

- `<name>` is what this repo calls the pack.
- `<folder>` holds the docs. It's read from your working tree, so it has no pin.

Any name and folder work. We suggest `project` and `docs/agents/project`:

```bash
npx context-packs add project docs/agents/project
```

Its block's start marker records the folder, `<!-- context-packs:start project path=docs/agents/project -->`. Its table points at the docs where they are, and only its nested packs' indexes are generated, into `docs/agents/generated/<name>/`. Resync after adding a doc or changing a `when:` line or a nested pack's rules.

## Decide when a pack loads

A pack's author suggests how it loads: if its `pack.md` has a `when`, it gets a row and loads only when that matches, and otherwise its rules are pasted into every session. An import pack follows that suggestion, which moves with `update`. To decide for yourself, add a line to its front matter and resync:

- `when: <when>` gives the pack a row with your `when`, whatever its author suggested.
- `when: always` pastes its rules into every session, even if its author gave it a `when`.

`add --when <when>` writes the line for you, `always` included. Anything you write below the front matter comes before the pack's own rules.

An import pack can also sit inside a pack of your own, such as your project's docs, to put several packs behind one row of yours, or to write rules beside them. Pass `--into` a folder in that pack:

```bash
npx context-packs add typescript https://github.com/acme/agent-context.git --path typescript \
  --into docs/agents/project --when 'Editing `**/*.ts`'
```

That writes `docs/agents/project/typescript/pack.md`, and the pack renders like a pack nested in yours, with no block of its own: a row in your pack's table, pointing at `docs/agents/generated/project/typescript/pack.md`, which holds its rules and its own table. Without a `when`, its rules and table would be pasted after your pack's own.

**Moving a pack.** Each marker in `AGENTS.md` names a root pack's folder, and the packs nested in it, yours or imported, render in its block. Inside a root, move a pack to any depth and resync, and it renders where it now sits. After moving a root pack, change `path=` in its start marker, or, if you moved it into another pack, run `remove <name>`: the block goes, and the moved folder stays. A pack moved out of every root drops out of `AGENTS.md`, as a doc moved out of a pack does.

[The example](docs/example.md#choosing-when-a-pack-loads) imports a pack this way, step by step. The tool keeps `from`, `path` and `ref`: `update` moves `ref`, and `remove typescript` deletes the folder. An import pack's folder holds only its `pack.md`, its name can't be used by another pack in the repo, and a pack from git can't hold one.

## Let your agent run it

The `context-packs` skill lets you skip the commands: ask Claude Code or Codex in plain words, and it runs them, shows you what changed, and leaves the result uncommitted for you to review. Install it for every project:

```bash
npx skills add mjewell/context-packs -g
```

Leave out `-g` to install it into the current project instead.

Then ask things like:

- "Add the context pack in the `context` folder of github.com/acme/agent-rules"
- "Update our context packs"
- "Install the typescript pack from team-rules"
- "Sync our project docs"

In Claude Code, `/context-packs` invokes it directly.

## Reference

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

**Pinning.** `--ref` takes a tag or a commit, never a branch, since a branch moves. `update` moves a pack pinned to a commit to the tip of the default branch, and one pinned to a release tag (a prefix and dot-separated numbers, such as `v1.2.0` or `acme-v3`) to the newest release with the same prefix, skipping pre-releases. Other tags stay put. A pack in a folder on disk, such as `.` or `../agent-rules`, isn't pinned.

**Edits stay upstream.** Each block ends with a hash of its text and the files under its `docs/agents/generated/<name>/`. If either was edited in the repo, the sync stops and says what to fix: change the pack in its origin, then `update`.

**Contributing.** [design.md](docs/agents/project/design.md) explains the choices behind the format. Run the tests with `python3 -m unittest discover tests`.
