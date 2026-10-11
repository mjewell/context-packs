# context-packs

Keep your coding agents' rules in one git repo, and sync them into the `AGENTS.md` of every repo that should follow them.

Agent rules copied from repo to repo drift apart. context-packs syncs them instead:

- **One source.** Every repo that installs a pack gets the same text, pinned to a tag or commit, and moves on with `update`.
- **Committed, so every session sees it.** Packs are copied in, not linked or loaded by a hook, so clones, CI and cloud agent sessions get them too.
- **Read only when relevant.** Long docs don't load into every session: `AGENTS.md` gets a table saying when to read each one.
- **Any agent.** Anything that reads `AGENTS.md` works, and `CLAUDE.md` is linked to it for Claude Code.

A synced pack in `AGENTS.md`:

```markdown
<!-- context-packs:start team-rules from=https://github.com/acme/agent-rules.git path=context ref=v1.2.0 -->
Prefer small PRs. Never commit secrets.

## team-rules context

| When | Read |
|---|---|
| Writing or changing tests | `docs/agents/packs/team-rules/testing.md` |
<!-- context-packs:end sha256:3f2c1aa0b9d4 -->
```

Run it with `npx context-packs`, or [let your agent run it](#let-your-agent-run-it). It needs `git`, Node 18+ and Python 3.9+; on macOS, the command line tools provide both `git` and Python.

## Write a pack

A pack is a folder in any git repo. `pack.md` holds the rules every session sees, and every other `.md` file is a doc agents read only when it's relevant. A folder holding a `pack.md` of its own is a nested pack, and a folder without one just groups files:

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

- `tier: required` installs it whenever its parent is installed. Without it, the nested pack is optional, and each repo picks it with `--docs`.
- `inline: true` pastes its rules and table after its parent's instead of giving it a row, for rules that apply whenever a repo has the nested pack, like a language's. A required inline pack needs no `when`.

```markdown
---
when: Working in a TypeScript repo
inline: true
---
Prefer unions to enums.
```

Any folder with a `pack.md` can also be installed on its own, as its own pack. Its front matter is ignored then, since it describes the folder as nested.

Keep `pack.md` short, since every session loads it.

Tags are optional. A repo pins to a commit by default, and `update` moves it to the tip of your default branch. Tag releases like `v1.2.0` once you want repos to pin to versions and `update` from one release to the next.

## Sync a pack from another repo

```bash
npx context-packs add <name> <git-url> --path <folder>
```

- `<name>` is what this repo calls the pack, such as `team-rules`.
- `<git-url>` is the repo holding the pack, as you'd pass it to `git clone`.
- `<folder>` is the pack's folder in that repo, such as `context`. Leave out `--path` if the pack is the whole repo.

That adds the pack's block to `AGENTS.md`, creating it if needed, and copies the docs into `docs/agents/packs/<name>/`, pinned to the origin's latest commit or to `--ref <tag or commit>`. Commit the result. If `AGENTS.md` already exists, the first run prints two marker lines to paste where the shared rules should go; then run it again.

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
