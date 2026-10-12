# context-packs

Pull the context your teams write for coding agents into each repo's `AGENTS.md`.

Whoever knows a topic writes its rules and docs once, as a pack: the auth team on sessions and permissions, the frontend team on forms and components. Each repo installs the packs that apply to it, alongside its own docs. The web app takes auth and frontend, and an API service takes auth, backend and database.

Two packs synced into a web app's `AGENTS.md`:

```markdown
<!-- context-packs:start auth from=https://github.com/acme/auth-service.git path=agent-pack ref=e60c2aac61c0e51fd90cf1406318dd785884bb19 -->
Never log tokens, session IDs or passwords, even at debug level.

## auth context

| When | Read |
|---|---|
| Adding an endpoint, or checking what a user may do | `docs/agents/packs/auth/permissions.md` |
| Reading the signed-in user, or changing sign-in or sign-out | `docs/agents/packs/auth/sessions.md` |
<!-- context-packs:end sha256:3ccb7c0b8f64 -->

<!-- context-packs:start frontend from=https://github.com/acme/agent-context.git path=frontend ref=frontend-v1.4.0 -->
Build UI from `@acme/ui` components; don't style raw HTML elements. Every user-facing string goes through `t()`.

## frontend context

| When | Read |
|---|---|
| Adding anything a user can click, type into or focus | `docs/agents/packs/frontend/accessibility.md` |
| Building or changing a form | `docs/agents/packs/frontend/forms.md` |
| Writing or changing React components | `docs/agents/packs/frontend/react.md` |
<!-- context-packs:end sha256:94fffbdf036a -->
```

[The full example](docs/example.md) shows the packs, the commands, and every file they generate.

- **Mix packs from anywhere.** A pack is a folder in any git repo, and each one gets its own block, pinned and updated on its own. Optional parts of a pack are installed only where a repo asks for them.
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

A nested pack gets a row too, from the `when` in its `pack.md`, pointing at a generated index that holds its rules and a table of its own docs and nested packs. Each nested pack is a read an agent makes before reaching the docs inside it, so nest only where a subtree is big and its `when` is sharp, and use plain folders to group the rest. Files other than `.md` files, such as code examples, are copied along with the docs beside them.

A nested pack is installed whenever its parent is. A part only some repos want, such as a language's rules, goes in a pack of its own, in a folder beside its parent's rather than inside it, and those repos install it with `add`.

Any folder with a `pack.md` can also be installed on its own, as its own pack, and it renders the way it would inside its parent. If its `pack.md` has a `when`, its block in `AGENTS.md` is a one-row table pointing at a generated index of its rules, so installing just `typescript` still loads its rules only when a row matches. Without a `when`, its rules are pasted into the block.

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

That adds the pack's block to your instruction file, creating `AGENTS.md` if you have none, and copies the docs into `docs/agents/packs/<name>/`, pinned to the origin's latest commit or to `--ref <tag or commit>`. Commit the result.

**Already have an `AGENTS.md` or `CLAUDE.md`?** Keep it. The first run prints two marker lines. Paste them wherever the packs should go, then run it again. If you have both files, paste them into the one that should hold the packs. The packs are synced in at that spot, and the rest of the file stays yours: no sync ever changes it. From then on, the file holding the packs is the one synced.

The sync leaves your other instruction file alone. If you keep a separate `CLAUDE.md` while the packs are in `AGENTS.md`, make sure Claude Code reads them, for example with an `@AGENTS.md` line in `CLAUDE.md`. With neither file, the sync creates `AGENTS.md` and links `CLAUDE.md` to it, so every agent reads the same rules.

Later, `npx context-packs update` moves packs to their latest version, and `npx context-packs` resyncs at the pinned ones. Private repos work, since origins are fetched with your own git credentials.

**Trying a pack before pushing it?** Pass the path of a folder beside the repo in place of the git URL: `npx context-packs add <name> ../agent-rules --path <folder>`. The sync reads that folder as it is on disk, like a pack in the repo itself, so there's no ref to pin, and the table points at the docs where they are. Edits to a doc show up without a resync. Changes to `pack.md` or a `when:` line need one, since those are copied into `AGENTS.md`. It syncs only where that folder exists, so it's for trying a pack out, not for a repo that clones, CI and cloud sessions sync.

## Sync your project's own docs

The same table works for a repo's own docs. Put them in a folder, each with a `when:` line, and install the folder as a pack read from the working tree:

```bash
npx context-packs add <name> . --path <folder>
```

- `<name>` is what this repo calls the pack.
- `.` is the origin: the pack is in this repo, so it has no ref and syncs from your working tree.
- `<folder>` holds the docs.

Any name and folder work. We suggest `project` and `docs/agents/project`:

```bash
npx context-packs add project . --path docs/agents/project
```

Its table points at the docs where they are, and only its nested packs' indexes are generated, into `docs/agents/packs/<name>/`. Resync after adding a doc or changing a `when:` line or a nested pack's rules.

## Decide when a pack loads

A pack's author decides how it loads: its rules are pasted into `AGENTS.md`, or, if its `pack.md` has a `when`, it gets a row and loads only when that matches. To make that call yourself, import the pack into your own docs instead of installing it on its own:

```bash
npx context-packs add typescript https://github.com/acme/agent-context.git --path typescript \
  --into docs/agents/project --when 'Editing `**/*.ts`'
```

This writes an import pack, `docs/agents/project/typescript/pack.md`, and syncs:

```markdown
---
when: Editing `**/*.ts`
from: https://github.com/acme/agent-context.git
path: typescript
ref: 3f2a9c1e0b7d4a6f8e5c2b1a9d8e7f6c5b4a3d2e
---
```

The imported pack becomes a pack nested in yours, with the import pack's `when` in place of its own:

- With a `when`, it gets a row in your pack's table, pointing at `docs/agents/packs/project/typescript/pack.md`, which holds its rules and its own table.
- Without one, its rules and table are pasted into your pack's block, after your pack's own.

[The example](docs/example.md#choosing-when-a-pack-loads) imports a pack this way, step by step. The `when` is yours to change, and so is anything you write below the front matter, which comes before the imported rules. The tool keeps the rest: `update` moves `ref`, and `remove typescript` deletes the folder. An import pack's folder holds only its `pack.md`, its name can't be used by another pack in the repo, and only a pack read from a folder on disk, such as your project's own docs, can hold one.

## Test a pack with evals

Check that agents read a doc when they should, and that it changes what they do, with tests that run through `claude plugin eval`, so running them needs Claude Code. A doc's tests go in a `.evals` folder beside it, under a folder named after the doc:

```text
context/
├── testing.md
└── .evals/
    └── testing/
        ├── triggers.md            # prompts that should and shouldn't make an agent read the doc
        └── writes-test-first/     # a case, in claude plugin eval's format
            ├── prompt.md          # the task, with front matter for the run
            └── graders/
                └── test-first.md  # how to score the run
```

`triggers.md` lists prompts under two headings. Each one runs as its own case, which passes when the agent reads the doc, for a prompt under `## Reads`, or doesn't, under `## Skips`:

````markdown
---
max_turns: 6
---
## Reads

- Add a test for the date parser
- CI failed with this, can you fix it?

  ```
  FAIL src/parse.test.ts > parses ISO dates
  ```

## Skips

- Bump the version to 0.4.0
````

Indent any further lines of a prompt under its `- `. Front matter, if any, goes to every prompt's run; without it, each run gets 6 turns and tools that look but change nothing (`Read`, `Glob` and `Grep`). Write other cases, such as one checking that the agent writes the test first, in `claude plugin eval`'s own format (see `claude plugin eval --help`).

The sync skips `.evals`, like every name starting with a dot, so tests stay with the pack and never reach the repos that install it. A nested pack's tests go in its own `.evals`.

Run a pack's cases from a repo that has the pack installed:

```bash
npx context-packs eval <name> [doc] [-- <claude plugin eval options>]
```

- `<name>` is the pack's name in this repo's `AGENTS.md`.
- `[doc]` is the doc whose tests to run, by its path in the pack without `.md`, such as `testing` or `typescript/types`. Leave it out to run every doc that has tests.
- Options after `--` go to `claude plugin eval`, such as `--runs 1 --model haiku`.

Each prompt in `triggers.md` runs with this repo's instructions as a sync writes them. Each case runs that way too, then again with the doc left out of the pack, keeping the rest of the pack and of `AGENTS.md`. It prints each score, each case's both ways, and the folder holding the reports and transcripts. To try a pack you're writing, install it from your working tree by a path such as `../agent-rules`, into an empty folder to test it alone, or into a repo whose instructions you want to test it with.

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
| `add <name> <origin> [--path P] [--ref R]` | Installs a pack, pinned to the origin's latest commit or to `--ref` |
| `add <name> <origin> --into F [--path P] [--ref R] [--when W]` | Imports a pack into the pack read from folder `F`, writing an import pack at `F/<name>/pack.md` |
| `remove <name>` | Uninstalls a pack, or deletes an import pack |
| `update [name…]` | Moves packs to their latest version |
| `update <name> --ref R` | Pins one pack to a tag or commit |
| `list` | Lists each pack, where it comes from, and its pin, with its import packs under it |
| `eval <name> [doc] [-- options]` | Runs a doc's tests: whether its triggers make an agent read it, and how its cases score with the doc and without it |

**Pinning.** `--ref` takes a tag or a commit, never a branch, since a branch moves. `update` moves a pack pinned to a commit to the tip of the default branch, and one pinned to a release tag (a prefix and dot-separated numbers, such as `v1.2.0` or `acme-v3`) to the newest release with the same prefix, skipping pre-releases. Other tags stay put. A pack in a folder on disk, such as `.` or `../agent-rules`, isn't pinned.

**Edits stay upstream.** Each block ends with a hash of its text and the files under its `docs/agents/packs/<name>/`. If either was edited in the repo, the sync stops and says what to fix: change the pack in its origin, then `update`.

**Contributing.** [design.md](docs/agents/project/design.md) explains the choices behind the format. Run the tests with `python3 -m unittest discover tests`.
