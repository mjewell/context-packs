# How packs load

An agent reads `AGENTS.md` in every session. Three rules decide what else it reads, and when:

- **A `when` puts content behind a lookup.** It becomes a row in a table, and the agent reads it only when the work matches. Every doc has one.
- **`when: always`, or no `when` on an added pack, inlines it.** Only a `pack.md` can be inlined: its rules sit wherever its parent's do, all the way up to `AGENTS.md` itself for an added pack.
- **A `pack.md` starts a new table** for the docs in its folder. A folder without one is just for organization: its docs join the nearest pack's table.

## Choosing when a pack loads

A pack's author suggests how it loads: if its `pack.md` has a `when`, it gets a row and loads only when that matches, and otherwise its rules are inlined into every session. A pack you install from git follows that suggestion, which moves with `update`, unless you choose for yourself:

| You want | Do |
|---|---|
| The pack loaded the way its author suggests | `add` it |
| Its rules in every session | `add … --when always` |
| Its rules behind a row you choose | `add … --when '<when>'` |
| Several packs behind one row of yours | [`add … --into <your pack's folder>`](#putting-packs-inside-your-own) |

`--when` writes a `when:` line into the pack's import pack, `docs/agents/<name>/pack.md`, the small file that records where the pack comes from. You can also edit that line yourself and resync. Anything you write below the import pack's front matter comes before the pack's own rules.

So `when` in a pack you write decides how it loads, while `when` in an import pack overrides its author's, and leaving it out keeps theirs.

## Putting packs inside your own

An import pack can also sit inside a pack of your own, such as [your project's docs](reference.md#installing-a-folder-on-disk), to put several packs behind one row of yours, or to write rules beside them. Pass `--into` a folder in that pack:

```bash
npx context-packs add typescript https://github.com/acme/agent-context.git --path typescript \
  --into docs/agents/project --when 'Editing `**/*.ts`'
```

That writes `docs/agents/project/typescript/pack.md`, and the pack renders like a pack nested in yours, with no block of its own: a row in your pack's table, pointing at `docs/agents/generated/project/typescript/pack.md`, which holds its rules and its own table. Without a `when`, its rules and table would be inlined after your pack's own.

`--into` is a shortcut, not the only way. An import pack is just a folder, so you can move one you've already added into your pack, such as `docs/agents/typescript/` to `docs/agents/project/typescript/`, and resync. The sync stops, since the pack's own block still points at its old folder, and tells you to run `remove typescript`. That drops the block and keeps the moved folder, which now renders inside your pack. To give it a row, add a `when:` line to its front matter.

[The example](example.md#choosing-when-a-pack-loads) imports a pack this way, step by step. The tool keeps `from`, `path` and `ref`: `update` moves `ref`, and `remove typescript` deletes the folder. An import pack's folder holds only its `pack.md`, its name can't be used by another pack in the repo, and a pack from git can't hold one.

## Moving a pack

Each marker in `AGENTS.md` names a root pack's folder, and the packs nested in it, yours or imported, render in its block. Inside a root, move a pack to any depth and resync, and it renders where it now sits. After moving a root pack, change `path=` in its start marker, or, if you moved it into another pack, run `remove <name>`: the block goes, and the moved folder stays. A pack moved out of every root drops out of `AGENTS.md`, as a doc moved out of a pack does.
