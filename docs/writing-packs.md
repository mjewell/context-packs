# Writing packs

A pack is a folder in any git repo. `pack.md` holds the rules every session sees, and every other `.md` file is a doc, read only when the `when` in its front matter matches the work. Files other than `.md` files, such as code examples, are copied along with the docs beside them.

This covers what goes past [the basics](../README.md#1-write-a-pack).

## Nested packs

A folder holding a `pack.md` of its own is a nested pack, and a folder without one just groups files:

```text
context/
├── pack.md          # rules inlined into every repo's AGENTS.md
├── testing.md       # a doc
├── git/
│   └── prs.md       # a doc, grouped in a folder
└── typescript/      # a nested pack
    ├── pack.md
    ├── types.md
    └── react/       # a nested pack inside it
        └── pack.md
```

A nested pack gets a row in its parent's table, from the `when` in its `pack.md`, pointing at a generated index that holds its rules and a table of its own docs and nested packs. One whose `when` is `always` is inlined after its parent's rules and table instead, for rules that matter whenever its parent does.

Each nested pack is a read an agent makes before reaching the docs inside it, so nest only where a subtree is big and its `when` is sharp, and use plain folders to group the rest.

A nested pack is installed whenever its parent is. A part only some repos want, such as a language's rules, goes in a pack of its own, in a folder beside its parent's rather than inside it, and those repos install it with `add`.

Any folder with a `pack.md` can also be installed on its own, as its own pack, and it renders the way it would inside its parent. If its `pack.md` has a `when`, it gets a row pointing at a generated index of its rules, so installing just `typescript` still loads its rules only when a row matches. Without a `when`, or with `when: always`, its rules are inlined.

## Pointing at another folder of the same repo

An import pack with a `path` and no `from` points at a folder of the repo it's in. In packs you publish, that lets several packs include one folder without copying it:

```text
agent-rules/
├── web/
│   ├── pack.md
│   └── typescript/
│       └── pack.md
├── api/
│   ├── pack.md
│   └── typescript/
│       └── pack.md
└── typescript/
    ├── pack.md
    └── types.md
```

`web/typescript/pack.md`, and the same in `api/`:

```markdown
---
path: typescript
---
```

A repo that installs `web` gets `agent-rules/typescript/` rendered at `web/typescript`, fetched at the same commit as `web`, so it needs no pin of its own and renders the same wherever `web` is installed. The path is relative to the repo's root, not to the file, so moving the import pack doesn't break it, and it can't leave the repo.

A repo that installs both `web` and `api` gets `typescript` in each, as each one's ref has it: if they're pinned to different commits or tags, each brings its own version. A pack from git can't import a pack from git, since that would bring pins of its own to keep in step.

## One repo or many

Once different people own different parts, each can write a pack of their own: the auth team on sessions and permissions, the frontend team on forms and components. Each repo installs the packs that apply to it. A web app takes auth and frontend, and an API service takes auth, backend and database.

A pack can sit beside the code it describes, such as an `agent-pack/` folder in the auth service, or in a repo that several teams share, with a folder for each. Each install is its own pack with its own pin, even when two come from the same repo, so choose based on who owns and releases what.

## Versions

Tags are optional. A repo pins to a commit by default, and `update` moves it to the tip of your default branch. Tag releases like `v1.2.0` once you want repos to pin to versions and `update` from one release to the next.

In a shared repo, give each pack's tags its own prefix, such as `frontend-v1.4.0` and `database-v2.0.0`, and `update` moves each pack along its own series. [Pinning](reference.md#pinning) has the details.

## Trying a pack before pushing it

Pass the path of a folder beside the repo in place of the git URL:

```bash
npx context-packs add <id> ../agent-rules --path <folder>
```

That writes an import pack whose `from` names that folder, with no ref. The folder is read as it is on disk, like your own docs, and the table points at the docs where they are. Edits to a doc show up without a resync. Changes to `pack.md` or a `when:` line need one, since those are copied into `AGENTS.md`. It syncs only where that folder exists, so it's for trying a pack out, not for a repo that clones, CI and cloud sessions sync.
