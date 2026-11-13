# context-packs

Write your agent docs as a set of files, and context-packs syncs them into your `AGENTS.md` as an index: a table that points your agent at the right doc only when it needs it.

You write:

```text
context-packs/
├── deploys.md    ---
│                 when: Deploying, or changing the deploy pipeline
│                 ---
│                 Deploy with `make deploy`, never by hand.
└── testing.md    ---
                  when: Writing or changing tests
                  ---
                  Build test records with the factories in `test/factories/`.
```

You run `npx context-packs`, and `AGENTS.md` gets this, after a short header:

```markdown
## Context

| When | Read |
|---|---|
| Deploying, or changing the deploy pipeline | `context-packs/deploys.md` |
| Writing or changing tests | `context-packs/testing.md` |
```

## Why use it

Instead of loading every doc into every session, `AGENTS.md` holds only the rules every session needs, plus a table telling the agent which doc to read for which task. You write those rules in a `pack.md`, and the sync copies them into `AGENTS.md` unchanged. In the example above, asked to write a test, the agent matches "Writing or changing tests" and reads `testing.md`. On any other task, it skips that file. This is the idea behind OpenAI's [Harness engineering](https://openai.com/index/harness-engineering/): keep `AGENTS.md` a short map that points to deeper docs. context-packs builds that map for you.

It also shares docs across repos. Once you use coding agents across several repos, the usual homes for your rules each break down:

- **A user-level file**, such as `~/.claude/CLAUDE.md`, isn't in any repo. Cloud sessions that check out only the repo never see it, and neither does anyone else working on it. It applies to every project, so you can't tailor it to one. Nothing versions it alongside the code it describes.
- **A copy in each repo's `AGENTS.md`** drifts as each copy is edited on its own.

With context-packs, you write rules and docs once, as a folder in any git repo: a *pack*. Each repo installs the packs it needs into its `context-packs/` folder, and the tool writes them into its `AGENTS.md`, committed with the code.

It works with any agent that reads `AGENTS.md` or `CLAUDE.md`. [The full example](docs/example.md) walks through the packs, the commands, and every file they generate.

## Quick start

You need `git`, Node 18+ and Python 3.9+. On macOS, the command line tools provide `git` and Python.

### 1. Write your repo's docs

Make a `context-packs/` folder of docs like the ones at the top. Add a `pack.md` for rules that go straight into `AGENTS.md`. Keep it short, since every session loads it. Every other `.md` file is a doc, and the `when` in its front matter becomes its row in the table.

### 2. Sync it

```bash
npx context-packs
```

That writes a block into `AGENTS.md` holding your rules, and a table with a row for each doc. Commit it, and clones, CI and cloud sessions all see it. After changing `pack.md` or a `when:` line, resync.

**Already have an `AGENTS.md` or `CLAUDE.md`?** Keep it. The first run prints two marker lines: paste them where the packs should go, and run it again. The sync only changes what's between them. With neither file, it creates `AGENTS.md` and links `CLAUDE.md` to it.

### 3. Share packs across repos

A pack can live in any git repo: one of its own, such as `agent-rules`, or a folder beside the code it describes. Push it, then in each repo that should have it:

```bash
npx context-packs add rules https://github.com/you/agent-rules.git --path <folder>
```

Leave out `--path` if the pack is the whole repo. That pins the pack to the repo's latest commit, and copies its docs into `context-packs/gen/rules/`. Private repos work, since packs are fetched with your own git credentials.

To change the pack, edit it at its source, push, and run `npx context-packs update` in each repo. If someone edits the generated copy instead, the next sync stops and says what to fix.

[Writing packs](docs/writing-packs.md) covers nesting packs for big topics, splitting packs as different people own different parts, pinning to tags, and trying a pack from a local folder before you push it.

Rather not type commands? [Let your agent run them](#let-your-agent-run-it).

## Common setups

| You want | Do |
|---|---|
| Rules every session sees, for this repo only | Write them in `AGENTS.md`, outside the context-packs block |
| Docs read only when relevant, for this repo only | [Write them in `context-packs/`](#1-write-your-repos-docs), and [sync](#2-sync-it) |
| Docs kept somewhere else in the repo | `add <id> <folder>`, which lists them where they are |
| Rules and docs shared across repos | [Push the pack to a git repo](#3-share-packs-across-repos), and `add` it in each repo |
| A pack held at a tag or commit | `add … --ref <tag or commit>` |
| CI to fail when the packs need a resync | Run `npx context-packs check`, as in [Checking in CI](docs/reference.md#checking-in-ci) |
| Every PR reviewed against the packs, with the findings posted to it | Add the `review` action, as in [Reviewing PRs in CI](docs/reference.md#reviewing-prs-in-ci) |
| To check an agent reads each doc when it should | Write prompts in its pack's `.evals/<doc>.md`, and run `npx context-packs eval`, as in [Testing when each doc gets read](docs/reference.md#testing-when-each-doc-gets-read) |
| A shared pack loaded differently than its author set up | See [How packs load](docs/loading.md#choosing-when-a-pack-loads) |

## Let your agent run it

The `context-packs` skill lets you skip the commands: ask Claude Code or Codex in plain words, and it runs them, shows you what changed, and leaves the result uncommitted for you to review. Install the skills for every project:

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

## Grow your packs with your agent

Four more skills help write and apply the rules themselves, and the command above installs them too:

- **`pack-rule`** writes one rule into the repo's packs, from a pattern you describe or examples you point at.
- **`pack-backfill`** finds a decision the code makes that no rule covers yet, and writes it once you confirm it.
- **`pack-findings`** checks a PR or branch against the repo's packs.
- **`pack-review`** goes through those findings with you, to decide whether the change or the rule needs fixing.

[Skills that grow your packs](docs/skills.md) covers how to run each one, and the `review` action that runs `pack-findings` on each PR in CI.

## Why not skills?

A doc with a `when` looks like a skill with a description. Skills suit procedures: steps to follow, scripts to run, a command to invoke. For what an agent should know before it starts, a table in `AGENTS.md` works better:

- **It gets read.** An agent reads `AGENTS.md` in every session, and is told to read a doc when its row matches. Whether a skill runs is the agent's call: in [Vercel's evals](https://vercel.com/blog/agents-md-outperforms-skills-in-our-agent-evals), skills went unused in over half the cases, and an index of docs in `AGENTS.md` beat them.
- **It nests.** Every skill's description sits in every session. A nested pack puts a whole subtree behind one row.
- **Rules and docs live together.** Rules every session needs are inlined beside the table, from the same pack.

Already sharing rules by symlinking Claude Code's `.claude/rules/`? See [Why not symlinked rules?](docs/why.md)

## Learn more

- [The full example](docs/example.md): two packs and a repo's own docs, from the files you write to the `AGENTS.md` you get.
- [Writing packs](docs/writing-packs.md): nested packs, one repo or many, pinning to tags, and trying a pack before pushing it.
- [How packs load](docs/loading.md): what goes into every session and what waits behind a row, and how to change that for a pack you install.
- [Reference](docs/reference.md): every command, pinning, and what the sync writes.
- [Skills that grow your packs](docs/skills.md): how to run `pack-rule`, `pack-backfill`, `pack-findings` and `pack-review`.
- [Why not symlinked rules?](docs/why.md): how `.claude/rules/` links load, and where they don't.
- [Design](context-packs/project/design.md): the choices behind the format. To contribute, run the tests with `python3 -m unittest discover tests`.
