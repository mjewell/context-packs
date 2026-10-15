# How packs load

An agent reads `AGENTS.md` in every session. Three rules decide what else it reads, and when:

- **A `when` puts content behind a lookup.** It becomes a row in a table, and the agent reads it only when the work matches. Every doc has one.
- **`when: always`, or no `when` on a pack you import, inlines it.** Only a `pack.md` can be inlined: its rules sit wherever its parent's do, all the way up to `AGENTS.md` itself for a pack in `context-packs/`.
- **A `pack.md` starts a new table** for the docs in its folder. A folder without one is just for organization: its docs join the nearest pack's table.

`context-packs/` is a pack too, the one at the top: its `pack.md`, if it has one, is inlined into `AGENTS.md`, and its docs get the `## Context` table.

## Choosing when a pack loads

A pack's author suggests how it loads: if its `pack.md` has a `when`, it gets a row and loads only when that matches, and otherwise its rules are inlined into every session. A pack you install follows that suggestion, which moves with `update`, unless you choose for yourself:

| You want | Do |
|---|---|
| The pack loaded the way its author suggests | `add` it |
| Its rules in every session | `add … --when always` |
| Its rules behind a row you choose | `add … --when '<when>'` |
| Several packs behind one row of yours | [Put them in a folder of yours](#grouping-packs) |

`--when` writes a `when:` line into the pack's import pack, `context-packs/<id>/pack.md`, the small file that records where the pack comes from. You can also edit that line yourself and resync. Anything you write below the import pack's front matter comes before the pack's own rules.

So `when` in a pack you write decides how it loads, while `when` in an import pack overrides its author's, and leaving it out keeps theirs.

## Grouping packs

An import pack renders wherever its folder sits in `context-packs/`. To put several packs behind one row of yours, or to write rules beside them, give a folder a `pack.md` with a `when`, and put their import packs inside it:

```bash
npx context-packs add server/database https://github.com/acme/agent-context.git --path database
```

```text
context-packs/
└── server/
    ├── pack.md          # when: Editing `server/**`
    └── database/
        └── pack.md      # the import pack
```

`AGENTS.md` gets one row, `Editing server/**`, pointing at `context-packs/gen/server.md`, which holds your rules, then the database pack's rules and table. Give the import pack a `when` of its own and it gets a row in that index instead.

[The example](example.md#choosing-when-a-pack-loads) adds a pack with a `when` of its own, step by step. The tool keeps `from`, `path` and `ref`: `update` moves `ref`, and `remove` deletes the folder. An import pack's folder holds only its `pack.md`.

## Moving a pack

Move a pack's folder anywhere in `context-packs/`, to any depth, and resync: it renders where it now sits, an import pack or one of your own. Its id, which `update` and `remove` take, is its new folder. A pack moved out of `context-packs/` drops out of `AGENTS.md`, as a doc moved out of a pack does.
