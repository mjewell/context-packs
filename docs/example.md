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

The web app has a few docs of its own, each with a `when:` line too:

```text
acme/web-app
└── docs/agents/project/
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

$ npx context-packs add project docs/agents/project
project: added
```

`auth` and `frontend` come from git, so each gets an import pack in `docs/agents/`, which says where the pack comes from and what it's pinned to: `auth` to the auth service's latest commit, and `frontend` to its release tag. `docs/agents/auth/pack.md`:

```markdown
---
from: https://github.com/acme/auth-service.git
path: agent-pack
ref: e60c2aac61c0e51fd90cf1406318dd785884bb19
---
```

`project` is read from the web app's own working tree, so it has no import pack and no pin. The web app doesn't install `backend` or `database`, so their rules stay out of its sessions. An API service would install those two, plus `auth`.

## What they generate

```text
acme/web-app
├── AGENTS.md                          # generated
├── CLAUDE.md -> AGENTS.md             # generated
└── docs/agents/
    ├── auth/pack.md                   # import pack: where auth comes from, and its pin
    ├── frontend/pack.md               # import pack for frontend
    ├── generated/                     # generated
    │   ├── auth/
    │   │   ├── permissions.md
    │   │   └── sessions.md
    │   └── frontend/
    │       ├── accessibility.md
    │       ├── forms.md
    │       ├── react.md               # index for the nested react pack
    │       └── react/
    │           └── testing.md
    └── project/                       # yours, left as it is
        ├── deploys.md
        └── routes.md
```

The web app had no instruction file yet, so the first `add` created `AGENTS.md` and linked `CLAUDE.md` to it. If it already had an `AGENTS.md` or `CLAUDE.md`, the packs would go into that file, wherever you placed two marker lines, and everything already in it would stay. See [Already have an `AGENTS.md` or `CLAUDE.md`?](reference.md#already-have-an-agentsmd-or-claudemd)

The docs under `generated/` are copies of the docs in each pack's repo. `AGENTS.md`, in full:

```markdown
<!-- context-packs:start header -->
## Context Packs

Context packs bring shared rules and docs in from elsewhere. Each pack has a block in this file holding its rules and a table of its context docs, and a doc may hold a table of its own. Before starting work that a row in any of these tables matches, read its doc. A pack's block, and everything under `docs/agents/generated/`, are generated from the folder its start marker names, and the import pack there if it has one: change them there, never here.
<!-- context-packs:end sha256:7b25770825f6 -->

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

<!-- context-packs:start project path=docs/agents/project -->
## project context

| When | Read |
|---|---|
| Deploying, or changing the deploy pipeline | `docs/agents/project/deploys.md` |
| Adding a page or route | `docs/agents/project/routes.md` |
<!-- context-packs:end sha256:3d908050ef2a -->
```

The nested `react` pack gets a row rather than having its rules inlined. The row points at a generated index, `react.md`, which holds its rules and its own table:

```markdown
Fetch data with the React Query hooks in `src/api/`, never in `useEffect`.

## frontend/react context

| When | Read |
|---|---|
| Writing or changing React component tests | `docs/agents/generated/frontend/react/testing.md` |
```

## What an agent does with it

Every session loads `AGENTS.md`: the header, the auth and frontend rules, and the three tables. That's a few dozen lines, however many docs sit behind them.

Asked to add a sign-up form, the agent matches "Building or changing a form" and reads `forms.md`. Adding a submit button also matches "Adding anything a user can click…", so it reads `accessibility.md`. Because the form is a React component, it reads `react.md`, which gives it the data-fetching rule and one more row to check. It never reads `deploys.md` or the auth docs, since nothing in the task matches them.

## Choosing when a pack loads

The web app keeps its sessions table in a small `db/` folder, so it wants the database team's rules, but only when it touches that folder. Added as it is, the `database` pack would inline its rules into every session, since its `pack.md` has no `when`: its team wrote it for API services, where nearly every task touches the database. So the web app adds it with a `when` of its own, and keeps its import pack in its own docs, so its row joins the `project` table. Without `--into`, it would get a block of its own holding the same row.

```console
$ npx context-packs add database https://github.com/acme/agent-context.git --path database --ref database-v2.0.0 --into docs/agents/project --when 'Editing `db/**`'
project: changed
database: added @ database-v2.0.0
```

That writes an import pack, `docs/agents/project/database/pack.md`. The `when` is the web app's to change, and `update` moves the `ref`:

```markdown
---
when: Editing `db/**`
from: https://github.com/acme/agent-context.git
path: database
ref: database-v2.0.0
---
```

The database rules stay out of `AGENTS.md`. The `project` block gets one row for them instead:

```markdown
<!-- context-packs:start project path=docs/agents/project -->
## project context

| When | Read |
|---|---|
| Editing `db/**` | `docs/agents/generated/project/database/pack.md` |
| Deploying, or changing the deploy pipeline | `docs/agents/project/deploys.md` |
| Adding a page or route | `docs/agents/project/routes.md` |
<!-- context-packs:end sha256:d662b7b0acbb -->
```

The row points at a generated index of the pack's rules and table, which only a session editing `db/` reads:

```markdown
Every query goes through the repositories in `src/db/`. Never write SQL in a request handler.

## database context

| When | Read |
|---|---|
| Writing or changing a migration | `docs/agents/generated/project/database/migrations.md` |
```

The pack's docs are copied beside the index, into `docs/agents/generated/project/database/`. An API service that installs the same pack in its `AGENTS.md` still gets the rules in every session: how a pack loads is each repo's call.

## Later

When the auth team changes its pack, they commit to `acme/auth-service` as usual. The web app picks up the change with `npx context-packs update auth`, which moves the pin to the latest commit. `update frontend` moves to the newest `frontend-v*` release and ignores `database-v*` tags. Each update is a normal diff to review and commit.

If someone edits a generated file in the web app, the next sync stops and says which pack it belongs to, so the fix goes back to that pack's repo.
