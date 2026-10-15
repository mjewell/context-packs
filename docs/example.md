# Example: a web app pulling in two teams' packs

At Acme, the auth team and the frontend team each write down what a coding agent should know about their area. The web app installs both, plus a pack of its own docs. This walks through every file involved: the packs, the commands, and what they generate.

## The packs

The auth team keeps its pack in its own service repo, next to the code it describes:

```text
acme/auth-service
├── src/…
└── agent-pack/
    ├── pack.md
    ├── permissions.md
    └── sessions.md
```

`pack.md` holds the rules every session sees:

```markdown
Never log tokens, session IDs or passwords, even at debug level.
```

Each other file is a doc an agent reads only when its `when` matches the work. `permissions.md`:

```markdown
---
when: Adding an endpoint, or checking what a user may do
---
# Permissions

Check permissions with `can(user, action, resource)` from `@acme/auth`. Never compare roles directly: roles change, actions don't.
```

The frontend team's pack is a folder in a repo that several teams share. It has a nested pack, `react/`, with its own rules and docs:

```text
acme/agent-context
├── backend/
│   └── pack.md
├── database/
│   ├── pack.md
│   └── migrations.md
└── frontend/
    ├── pack.md
    ├── accessibility.md
    ├── forms.md
    └── react/
        ├── pack.md
        └── testing.md
```

Each team tags its own releases with a prefix, such as `frontend-v1.4.0` and `database-v2.0.0`, so `update` moves each pack along its own series.

`react/pack.md` starts with front matter saying when to read it, like a doc:

```markdown
---
when: Writing or changing React components
---
Fetch data with the React Query hooks in `src/api/`, never in `useEffect`.
```

The web app has a few docs of its own, each with a `when:` line too, in its `context-packs/` folder:

```text
acme/web-app
└── context-packs/
    ├── deploys.md
    └── routes.md
```

## The commands

In `acme/web-app`:

```console
$ npx context-packs add auth https://github.com/acme/auth-service.git --path agent-pack
Created AGENTS.md
Linked CLAUDE.md to AGENTS.md
auth: added @ e60c2aa

$ npx context-packs add frontend https://github.com/acme/agent-context.git --path frontend --ref frontend-v1.4.0
frontend: added @ frontend-v1.4.0
```

Each `add` writes an import pack in `context-packs/`, which says where the pack comes from and what it's pinned to: `auth` to the auth service's latest commit, and `frontend` to its release tag. `context-packs/auth/pack.md`:

```markdown
---
from: https://github.com/acme/auth-service.git
path: agent-pack
ref: e60c2aac61c0e51fd90cf1406318dd785884bb19
---
```

The web app's own docs need no command: everything in `context-packs/` syncs, read from the working tree. The web app doesn't install `backend` or `database`, so their rules stay out of its sessions. An API service would install those two, plus `auth`.

## What they generate

```text
acme/web-app
├── AGENTS.md                          # generated
├── CLAUDE.md -> AGENTS.md             # generated
└── context-packs/
    ├── auth/pack.md                   # import pack: where auth comes from, and its pin
    ├── frontend/pack.md               # import pack for frontend
    ├── deploys.md                     # yours, left as it is
    ├── routes.md
    └── gen/                           # generated
        ├── auth/
        │   ├── permissions.md
        │   └── sessions.md
        └── frontend/
            ├── accessibility.md
            ├── forms.md
            ├── react.md               # index for the nested react pack
            └── react/
                └── testing.md
```

The web app had no instruction file yet, so the first `add` created `AGENTS.md` and linked `CLAUDE.md` to it. If it already had an `AGENTS.md` or `CLAUDE.md`, the packs would go into that file, wherever you placed two marker lines, and everything already in it would stay. See [Already have an `AGENTS.md` or `CLAUDE.md`?](reference.md#already-have-an-agentsmd-or-claudemd)

The docs under `gen/` are copies of the docs in each pack's repo. `AGENTS.md`, in full:

```markdown
<!-- context-packs:start -->
## Context Packs

Context packs bring shared rules and docs in from elsewhere. Each pack has its rules and a table of its context docs here, and a doc may hold a table of its own. Before starting work that a row in any of these tables matches, read its doc. The packs here, and everything under `context-packs/gen/`, are generated from `context-packs/`: change them there, never here.

## Context

| When | Read |
|---|---|
| Deploying, or changing the deploy pipeline | `context-packs/deploys.md` |
| Adding a page or route | `context-packs/routes.md` |

<!-- context-packs:pack auth -->
Never log tokens, session IDs or passwords, even at debug level.

## auth context

| When | Read |
|---|---|
| Adding an endpoint, or checking what a user may do | `context-packs/gen/auth/permissions.md` |
| Reading the signed-in user, or changing sign-in or sign-out | `context-packs/gen/auth/sessions.md` |
<!-- context-packs:pack-end auth -->

<!-- context-packs:pack frontend -->
Build UI from `@acme/ui` components; don't style raw HTML elements. Every user-facing string goes through `t()`.

## frontend context

| When | Read |
|---|---|
| Adding anything a user can click, type into or focus | `context-packs/gen/frontend/accessibility.md` |
| Building or changing a form | `context-packs/gen/frontend/forms.md` |
| Writing or changing React components | `context-packs/gen/frontend/react.md` |
<!-- context-packs:pack-end frontend -->
<!-- context-packs:end sha256:513899ce75f9 -->
```

The web app's own docs come first, in the `## Context` table, followed by each pack in the order of its folder. Each pack sits between comments naming its folder in `context-packs/`, which show people reading the file where it starts and ends; the sync doesn't read them, and Claude Code strips them before an agent sees the file.

The nested `react` pack gets a row rather than having its rules inlined. The row points at a generated index, `react.md`, which holds its rules and its own table:

```markdown
Fetch data with the React Query hooks in `src/api/`, never in `useEffect`.

## frontend/react context

| When | Read |
|---|---|
| Writing or changing React component tests | `context-packs/gen/frontend/react/testing.md` |
```

## What an agent does with it

Every session loads `AGENTS.md`: the header, the auth and frontend rules, and the three tables. That's a few dozen lines, however many docs sit behind them.

Asked to add a sign-up form, the agent matches "Building or changing a form" and reads `forms.md`. Adding a submit button also matches "Adding anything a user can click…", so it reads `accessibility.md`. Because the form is a React component, it reads `react.md`, which gives it the data-fetching rule and one more row to check. It never reads `deploys.md` or the auth docs, since nothing in the task matches them.

## Choosing when a pack loads

The web app keeps its sessions table in a small `db/` folder, so it wants the database team's rules, but only when it touches that folder. Added as it is, the `database` pack would inline its rules into every session, since its `pack.md` has no `when`: its team wrote it for API services, where nearly every task touches the database. So the web app adds it with a `when` of its own:

```console
$ npx context-packs add database https://github.com/acme/agent-context.git --path database --ref database-v2.0.0 --when 'Editing `db/**`'
database: added @ database-v2.0.0
```

That writes an import pack, `context-packs/database/pack.md`. The `when` is the web app's to change, and `update` moves the `ref`:

```markdown
---
when: Editing `db/**`
from: https://github.com/acme/agent-context.git
path: database
ref: database-v2.0.0
---
```

The database rules stay out of `AGENTS.md`. The `## Context` table gets one row for them instead:

```markdown
## Context

| When | Read |
|---|---|
| Editing `db/**` | `context-packs/gen/database/pack.md` |
| Deploying, or changing the deploy pipeline | `context-packs/deploys.md` |
| Adding a page or route | `context-packs/routes.md` |
```

The row points at a generated index of the pack's rules and table, which only a session editing `db/` reads:

```markdown
Every query goes through the repositories in `src/db/`. Never write SQL in a request handler.

## database context

| When | Read |
|---|---|
| Writing or changing a migration | `context-packs/gen/database/migrations.md` |
```

The pack's docs are copied beside the index, into `context-packs/gen/database/`. An API service that installs the same pack still gets the rules in every session: how a pack loads is each repo's call.

If the web app later wants its server rules behind one row, it can write `context-packs/server/pack.md` with a `when` of its own and move the `database` folder inside it. The next sync renders the database pack there, with nothing else to change. See [Grouping packs](loading.md#grouping-packs).

## Later

When the auth team changes its pack, they commit to `acme/auth-service` as usual. The web app picks up the change with `npx context-packs update auth`, which moves the pin to the latest commit. `update frontend` moves to the newest `frontend-v*` release and ignores `database-v*` tags. Each update is a normal diff to review and commit.

If someone edits a generated file in the web app, the next sync stops and says so, so the fix goes back to that pack's repo.
