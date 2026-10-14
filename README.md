# context-packs

Share coding-agent rules and docs across repos, and keep each repo's `AGENTS.md` short.

Once you use coding agents across several repos, the usual homes for your rules each break down:

- **A user-level file**, such as `~/.claude/CLAUDE.md`, isn't in any repo. Cloud sessions that check out only the repo never see it, and neither does anyone else working on it. It applies to every project, so you can't tailor it to one. Nothing versions it alongside the code it describes.
- **A copy in each repo's `AGENTS.md`** drifts as each copy is edited on its own.

With context-packs, you write rules and docs once, as a folder in any git repo: a *pack*. Each repo installs the packs it needs, and the tool writes them into its `AGENTS.md`, committed with the code.

It also keeps that file short. Instead of loading every doc into every session, `AGENTS.md` holds only the rules every session needs, plus a table telling the agent which doc to read for which task. Two packs synced into a web app's `AGENTS.md`:

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

Every session reads both packs' rules. Asked to build a form, the agent matches "Building or changing a form" and reads `forms.md`, and it never opens the auth docs unless the task touches them. This is the idea behind OpenAI's [Harness engineering](https://openai.com/index/harness-engineering/): keep `AGENTS.md` a short map that points to deeper docs. context-packs builds that map for you, and shares it across repos.

It works with any agent that reads `AGENTS.md` or `CLAUDE.md`. [The full example](docs/example.md) walks through the packs, the commands, and every file they generate.

## Quick start

You need `git`, Node 18+ and Python 3.9+. On macOS, the command line tools provide `git` and Python.

### 1. Write a pack

A pack is a folder. Start with one in your repo:

```text
docs/agents/project/
├── pack.md       # rules every session sees
└── testing.md    # a doc, read only when its `when` matches
```

`pack.md` holds rules that go straight into `AGENTS.md`. Keep it short, since every session loads it:

```markdown
Run `npm run lint` before saying a change is done.
```

Every other `.md` file is a doc. It starts with front matter whose `when` becomes its row in the table, telling the agent when to read it:

```markdown
---
when: Writing or changing tests
---
Build test records with the factories in `test/factories/`, never by hand.
```

### 2. Install it

```bash
npx context-packs add project docs/agents/project
```

That adds a block to `AGENTS.md` holding your rules, and a table with a row for `testing.md`. Commit it, and clones, CI and cloud sessions all see it. After changing `pack.md` or a `when:` line, resync with `npx context-packs`.

**Already have an `AGENTS.md` or `CLAUDE.md`?** Keep it. The first run prints two marker lines: paste them where the packs should go, and run it again. The sync only changes what's between markers. With neither file, it creates `AGENTS.md` and links `CLAUDE.md` to it.

### 3. Share it across repos

A pack can live in any git repo: one of its own, such as `agent-rules`, or a folder beside the code it describes. Push it, then in each repo that should have it:

```bash
npx context-packs add rules https://github.com/you/agent-rules.git --path <folder>
```

Leave out `--path` if the pack is the whole repo. That pins the pack to the repo's latest commit and copies its docs into `docs/agents/generated/rules/`. Private repos work, since packs are fetched with your own git credentials.

To change the pack, edit it at its source, push, and run `npx context-packs update` in each repo. If someone edits the generated copy instead, the next sync stops and says which pack to fix.

[Writing packs](docs/writing-packs.md) covers nesting packs for big topics, splitting packs as different people own different parts, tagging releases, and trying a pack from a local folder before you push it.

Rather not type commands? [Let your agent run them](#let-your-agent-run-it).

## Common setups

| You want | Do |
|---|---|
| Rules every session sees, for this repo only | Write them in `AGENTS.md`, outside the packs' blocks |
| Docs read only when relevant, for this repo only | [Write a pack](#1-write-a-pack) in the repo, and [install it](#2-install-it) |
| Rules and docs shared across repos | [Push the pack to a git repo](#3-share-it-across-repos), and `add` it in each repo |
| A pack pinned to a release | `add … --ref <tag or commit>` |
| A shared pack loaded differently than its author set up | See [How packs load](docs/loading.md#choosing-when-a-pack-loads) |

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

## Why not skills?

A doc with a `when` looks like a skill with a description. Skills suit procedures: steps to follow, scripts to run, a command to invoke. For what an agent should know before it starts, a table in `AGENTS.md` works better:

- **It gets read.** An agent reads `AGENTS.md` in every session, and is told to read a doc when its row matches. Whether a skill runs is the agent's call: in [Vercel's evals](https://vercel.com/blog/agents-md-outperforms-skills-in-our-agent-evals), skills went unused in over half the cases, and an index of docs in `AGENTS.md` beat them.
- **It nests.** Every skill's description sits in every session. A nested pack puts a whole subtree behind one row.
- **Rules and docs live together.** Rules every session needs are inlined beside the table, from the same pack.

## Learn more

- [The full example](docs/example.md): two packs and a repo's own docs, from the files you write to the `AGENTS.md` you get.
- [Writing packs](docs/writing-packs.md): nested packs, one repo or many, release tags, and trying a pack before pushing it.
- [How packs load](docs/loading.md): what goes into every session and what waits behind a row, and how to change that for a pack you install.
- [Reference](docs/reference.md): every command, pinning, and what the sync writes.
- [Design](docs/agents/project/design.md): the choices behind the format. To contribute, run the tests with `python3 -m unittest discover tests`.
