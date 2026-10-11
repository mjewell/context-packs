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

<!-- context-packs:start frontend from=https://github.com/acme/agent-context.git path=frontend ref=frontend-v1.4.0 docs=react -->
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

A nested pack's `pack.md` takes two more fields:

- `optional: true` leaves it out unless a repo picks it with `--docs`. Without it, the nested pack is installed whenever its parent is.
- `inline: true` pastes its rules and table after its parent's instead of giving it a row, for rules that apply whenever a repo has the nested pack, like a language's. An inline pack that isn't optional needs no `when`.

```markdown
---
when: Working in a TypeScript repo
optional: true
inline: true
---
Prefer unions to enums.
```

Any folder with a `pack.md` can also be installed on its own, as its own pack, and it renders the way it would inside its parent. If its `pack.md` has a `when` and isn't inline, its block in `AGENTS.md` is a one-row table pointing at a generated index of its rules, so installing just `typescript` still loads its rules only when a row matches. Without a `when`, or with `inline: true`, its rules are pasted into the block. `optional` doesn't apply, since installing it is the pick.

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
| `add <name> <origin> [--path P] [--ref R] [--docs a,b]` | Installs a pack, pinned to the origin's latest commit or to `--ref`, with the optional nested packs in `--docs` |
| `remove <name>` | Uninstalls a pack |
| `update [name…]` | Moves packs to their latest version |
| `update <name> --ref R` | Pins one pack to a tag or commit |
| `docs <name> a,b` | Replaces the optional nested packs a pack installs, each named by its path such as `typescript/react` (`''` for none). Picking one installs the packs above it |
| `list` | Lists each pack and its nested packs as a tree, marking the installed ones |

**Pinning.** `--ref` takes a tag or a commit, never a branch, since a branch moves. `update` moves a pack pinned to a commit to the tip of the default branch, and one pinned to a release tag (a prefix and dot-separated numbers, such as `v1.2.0` or `acme-v3`) to the newest release with the same prefix, skipping pre-releases. Other tags stay put.

**Edits stay upstream.** Each block ends with a hash of its text and the files under its `docs/agents/packs/<name>/`. If either was edited in the repo, the sync stops and says what to fix: change the pack in its origin, then `update`.

**Contributing.** [design.md](docs/agents/project/design.md) explains the choices behind the format. Run the tests with `python3 -m unittest discover tests`.
