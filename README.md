# context-packs

Sync shared agent rules and docs into each repo's `AGENTS.md`.

A context pack is a folder in a git repo holding rules every agent session should see, and docs that agents read only for some kinds of work. `context-packs` copies the packs a repo installs into that repo, pinned to a tag or commit, so Claude Code, Codex and any other agent that reads `AGENTS.md` get the same rules. That includes cloud sessions and fresh clones, which see only what's committed.

## Install

Run it with npx:

```bash
npx github:mjewell/context-packs <repo> <command>
```

It needs `git`, Node 18 or later, and Python 3.9 or later. On macOS, the Xcode command line tools that provide `git` provide Python too.

This repo is also a Claude Code plugin with a `/context-packs` skill, which runs the commands for you. Add it to a plugin marketplace, or install it from GitHub.

## Use it

```bash
npx github:mjewell/context-packs . add team-rules https://github.com/acme/agent-rules.git --path context
```

That writes two blocks into `AGENTS.md`: a header block explaining context packs, and one for the pack. It also copies the pack's doc sets into `docs/agents/packs/team-rules/`, and creates `CLAUDE.md` as a symlink to `AGENTS.md`, so Claude Code reads the same file. Commit the result.

If `AGENTS.md` already exists, the first run prints two marker lines instead. Paste them where the shared rules should go, after the intro and before the project-specific sections, and run it again.

| Command | Does |
|---|---|
| *(none)* | Resyncs every pack at its pinned ref |
| `add <name> <origin> [--path P] [--ref R] [--docs a,b]` | Installs a pack, pinned to the origin's latest commit or to `--ref` |
| `remove <name>` | Uninstalls a pack |
| `update [name…]` | Moves packs to their latest version |
| `update <name> --ref R` | Pins one pack to a tag or commit |
| `docs <name> a,b` | Replaces a pack's optional doc sets (`''` for none) |
| `list` | Lists each pack and its doc sets, marking the installed ones |

Pass `--workspace` before the command to sync a folder that holds several repos but isn't one itself. It gets the packs but no `CLAUDE.md`, since one there would make Claude Code load the workspace's rules inside every repo too.

### Pinning and updates

Each pack's start marker records where it comes from and where it's pinned:

```markdown
<!-- context-packs:start team-rules from=https://github.com/acme/agent-rules.git path=context ref=v1.2.0 -->
```

`--ref` takes a tag or a commit, never a branch, since a branch moves. `update` moves a pack along what it's pinned to:

- **A commit** moves to the tip of the origin's default branch.
- **A release tag**, meaning a prefix followed by dot-separated numbers such as `v1.2.0` or `acme-v3`, moves to the newest release with the same prefix. Pre-releases like `v2.0.0-rc1` are skipped.
- **Any other tag** stays put.

The sync fetches origins into `~/.cache/context-packs/` using your own git credentials, so private repos work.

A pack can also live in the repo it's synced into: `add <name> . --path <folder>` reads it from the working tree, with no ref. Its table points at the docs where they are instead of copying them, and it installs every doc set it has.

That's the way to keep a repo's own context docs. Put each one in `docs/agents/project/` with a `when:` line, run `add project . --path docs/agents/project` once, and resync after adding a doc or changing its `when:`. The table in `AGENTS.md` stays generated from the docs.

### Edits stay upstream

Each block ends with a hash covering its text and its docs folder. If either was edited in the repo, the sync stops without changing anything and says what to fix. Change a pack in its origin, then update.

## Write a pack

A pack is a folder holding an optional `agents.md` and any number of doc sets. A doc set is a single `.md` file, or a folder whose `index.md` links to its other files:

```text
context/
├── agents.md           # rules pasted into the pack's block
├── testing.md          # a doc set in one file
└── typescript/
    ├── index.md        # a doc set's entry point
    └── react.md        # other files, linked from index.md
```

Each doc set's entry point starts with front matter saying when to read it:

```markdown
---
when: Writing or changing tests, or fixing a bug
tier: required
---
```

The pack's block lists its installed doc sets in a table that agents check before starting work. `tier: required` installs the set in every repo that installs the pack. Leave `tier` out for an optional set, which each repo chooses with `--docs` or `docs`.

Keep `agents.md` small, since every session loads it, and put anything needed only for some work in a doc set. agy stops reading `AGENTS.md` after 24 KB.

## Tests

```bash
python3 -m unittest discover tests
```
