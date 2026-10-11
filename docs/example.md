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
│   └── pack.md
└── frontend/
    ├── pack.md
    ├── accessibility.md
    ├── forms.md
    └── react/
        ├── pack.md
        └── testing.md
```

Each team tags its own releases with a prefix, such as `frontend-v1.4.0` and `database-v2.0.0`, so `update` moves each pack along its own series.

`react/pack.md` is optional, so a repo only gets it by asking for it:

```markdown
---
when: Writing or changing React components
optional: true
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

$ npx context-packs add frontend https://github.com/acme/agent-context.git --path frontend --ref frontend-v1.4.0 --docs react
frontend: added @ frontend-v1.4.0 (docs: react)

$ npx context-packs add project . --path docs/agents/project
project: added
```

`auth` is pinned to the auth service's latest commit, and `frontend` to its release tag. `project` is read from the web app's own working tree, so it has no pin. The web app doesn't install `backend` or `database`, so their rules stay out of its sessions. An API service would install those two, plus `auth`.

## What they generate

```text
acme/web-app
├── AGENTS.md                          # generated
├── CLAUDE.md -> AGENTS.md             # generated
└── docs/agents/
    ├── packs/                         # generated
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

The web app had no instruction file yet, so the first `add` created `AGENTS.md` and linked `CLAUDE.md` to it. If it already had an `AGENTS.md` or `CLAUDE.md`, the packs would go into that file, wherever you placed two marker lines, and everything already in it would stay. See [Already have an `AGENTS.md` or `CLAUDE.md`?](../README.md#sync-a-pack-from-another-repo)

The docs under `packs/` are copies of the docs in each pack's repo. `AGENTS.md`, in full:

```markdown
<!-- context-packs:start header -->
## Context Packs

Context packs bring shared rules and docs in from elsewhere. Each pack has a block in this file holding its rules and a table of its context docs, and a doc may hold a table of its own. Before starting work that a row in any of these tables matches, read its doc. A pack's block, and everything under `docs/agents/packs/`, are generated from the `from` and `path` in the block's start marker: change them there, never here.
<!-- context-packs:end sha256:9ca6e3aa65e7 -->

<!-- context-packs:start auth from=https://github.com/acme/auth-service.git path=agent-pack ref=e60c2aac61c0e51fd90cf1406318dd785884bb19 -->
Never log tokens, session IDs or passwords, even at debug level.

## auth context

| When | Read |
|---|---|
| Adding an endpoint, or checking what a user may do | `docs/agents/packs/auth/permissions.md` |
| Reading the signed-in user, or changing sign-in or sign-out | `docs/agents/packs/auth/sessions.md` |
<!-- context-packs:end sha256:3ccb7c0b8f64 -->

<!-- context-packs:start frontend from=https://github.com/acme/agent-context.git path=frontend ref=frontend-v1.4.0 docs=react -->
Build UI from `@acme/ui` components; don't style raw HTML elements. Every user-facing string goes through `t()`.

## frontend context

| When | Read |
|---|---|
| Adding anything a user can click, type into or focus | `docs/agents/packs/frontend/accessibility.md` |
| Building or changing a form | `docs/agents/packs/frontend/forms.md` |
| Writing or changing React components | `docs/agents/packs/frontend/react.md` |
<!-- context-packs:end sha256:94fffbdf036a -->

<!-- context-packs:start project from=. path=docs/agents/project -->
## project context

| When | Read |
|---|---|
| Deploying, or changing the deploy pipeline | `docs/agents/project/deploys.md` |
| Adding a page or route | `docs/agents/project/routes.md` |
<!-- context-packs:end sha256:3d908050ef2a -->
```

The nested `react` pack gets a row rather than having its rules pasted in. The row points at a generated index, `react.md`, which holds its rules and its own table:

```markdown
Fetch data with the React Query hooks in `src/api/`, never in `useEffect`.

## frontend/react context

| When | Read |
|---|---|
| Writing or changing React component tests | `docs/agents/packs/frontend/react/testing.md` |
```

## What an agent does with it

Every session loads `AGENTS.md`: the header, the auth and frontend rules, and the three tables. That's a few dozen lines, however many docs sit behind them.

Asked to add a sign-up form, the agent matches "Building or changing a form" and reads `forms.md`. Adding a submit button also matches "Adding anything a user can click…", so it reads `accessibility.md`. Because the form is a React component, it reads `react.md`, which gives it the data-fetching rule and one more row to check. It never reads `deploys.md` or the auth docs, since nothing in the task matches them.

## Later

When the auth team changes its pack, they commit to `acme/auth-service` as usual. The web app picks up the change with `npx context-packs update auth`, which moves the pin to the latest commit. `update frontend` moves to the newest `frontend-v*` release and ignores `database-v*` tags. Each update is a normal diff to review and commit.

If someone edits a generated file in the web app, the next sync stops and says which pack it belongs to, so the fix goes back to that pack's repo.
