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

Run it with `npx context-packs`. It needs `git`, Node 18+ and Python 3.9+; on macOS, the command line tools provide both `git` and Python.

## Write a pack

A pack is a folder in any git repo. `pack.md` holds the rules every session sees, and each doc set, one `.md` file or a folder with an `index.md`, covers a topic agents read about only when it's relevant:

```text
context/
├── pack.md          # rules pasted into every repo's AGENTS.md
├── testing.md       # a doc set in one file
└── typescript/
    ├── index.md     # a doc set's entry point
    └── react.md     # linked from index.md
```

Each doc set starts with front matter. `when` becomes its row in the table, and `tier: required` installs it in every repo; without it, the set is optional and each repo chooses it with `--docs`.

```markdown
---
when: Writing or changing tests
tier: required
---
```

Keep `pack.md` short, since every session loads it.

Tags are optional. A repo pins to a commit by default, and `update` moves it to the tip of your default branch. Tag releases like `v1.2.0` once you want repos to pin to versions and `update` from one release to the next.

## Sync a pack from another repo

```bash
npx context-packs add <name> <git-url> --path <folder>
```

- `<name>` is what this repo calls the pack, such as `team-rules`.
- `<git-url>` is the repo holding the pack, as you'd pass it to `git clone`.
- `<folder>` is the pack's folder in that repo, such as `context`. Leave out `--path` if the pack is the whole repo.

That adds the pack's block to `AGENTS.md`, creating it if needed, and copies the doc sets into `docs/agents/packs/<name>/`, pinned to the origin's latest commit or to `--ref <tag or commit>`. Commit the result. If `AGENTS.md` already exists, the first run prints two marker lines to paste where the shared rules should go; then run it again.

Later, `npx context-packs update` moves packs to their latest version, and `npx context-packs` resyncs at the pinned ones. Private repos work, since origins are fetched with your own git credentials.

## Sync your project's own docs

The same table works for a repo's own docs. Put each in a folder with a `when:` line, and install the folder as a pack read from the working tree. Any folder works; `docs/agents/project/` is just a suggestion:

```bash
npx context-packs add project . --path docs/agents/project
```

Its table points at the docs where they are. Resync after adding a doc or changing a `when:` line.

## Reference

Each command syncs the current folder, or `--dir <folder>`, and prints what changed. The folder can also hold several repos without being one, so sessions started there get the rules too.

| Command | Does |
|---|---|
| *(none)* | Resyncs every pack at its pinned ref |
| `add <name> <origin> [--path P] [--ref R] [--docs a,b]` | Installs a pack, pinned to the origin's latest commit or to `--ref` |
| `remove <name>` | Uninstalls a pack |
| `update [name…]` | Moves packs to their latest version |
| `update <name> --ref R` | Pins one pack to a tag or commit |
| `docs <name> a,b` | Replaces a pack's optional doc sets (`''` for none) |
| `list` | Lists each pack and its doc sets, marking the installed ones |

**Pinning.** `--ref` takes a tag or a commit, never a branch, since a branch moves. `update` moves a pack pinned to a commit to the tip of the default branch, and one pinned to a release tag (a prefix and dot-separated numbers, such as `v1.2.0` or `acme-v3`) to the newest release with the same prefix, skipping pre-releases. Other tags stay put.

**Edits stay upstream.** Each block ends with a hash of its text and synced docs. If either was edited in the repo, the sync stops and says what to fix: change the pack in its origin, then `update`.

**Claude Code skill.** This repo is also a Claude Code plugin whose `/context-packs` skill runs the commands for you. To install just the skill for Claude Code and Codex: `npx skills add mjewell/context-packs -g -a claude-code -a codex`.

**Contributing.** [design.md](docs/agents/project/design.md) explains the choices behind the format. Run the tests with `python3 -m unittest discover tests`.
