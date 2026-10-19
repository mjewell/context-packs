# Testing your `when`s

A row only helps if an agent reads its doc when the work matches, and leaves it alone otherwise. You can check that with [promptfoo](https://www.promptfoo.dev): each case is a task, run as a real Claude Code session against your synced `AGENTS.md`, and graded on which docs the session read. context-packs ships the grader, `reads.js`.

Runs use real tokens, about 30k each, so they're something to run after changing a `when`, not on every commit.

## Set up

In a folder of its own, such as `evals/`:

```bash
npm install --save-dev promptfoo @anthropic-ai/claude-agent-sdk context-packs
```

`promptfooconfig.yaml`:

```yaml
prompts:
  - '{{task}}'

providers:
  - id: anthropic:claude-agent-sdk
    config:
      apiKeyRequired: false    # use your Claude Code login instead of ANTHROPIC_API_KEY
      working_dir: ./fixture
      copy_working_dir: true   # run each case in a fresh copy outside your folders
      setting_sources: ['project']
      max_turns: 8
      persist_session: false

defaultTest:
  assert:
    - type: javascript
      value: file://node_modules/context-packs/evals/reads.js

tests:
  - vars:
      task: The date parser returns the wrong month for ISO strings. Fix it.
      reads: testing.md
  - vars:
      task: Explain how parseIsoDate works.
      skips: testing.md
  - vars:
      task: Fix the typo "teh" in README.md.
```

Run it with `npx promptfoo eval`, and add `--repeat 3` to see whether a result holds up.

## Cases

- `reads`: docs the session must read. `skips`: docs it must not. Each is comma-separated, and names a doc by the end of its path, such as `testing.md`, or `core/testing.md` when two packs have a `testing.md`.
- With neither, the session must read no doc at all.
- A doc is a Markdown file under `context-packs/`. If yours live somewhere else, set `docs` to that folder, such as `docs: packs/core/` in `defaultTest`'s `vars`.
- The grader's reason lists every doc the session read, so a case that passes still shows which other rows it pulled in.

Near misses are the cases worth writing: tasks close to a row's `when` that shouldn't match it, or that match only through a clause that's easy to miss.

## The fixture

The session sees only `working_dir`, so make it a repo with code to act on. A bug-fix task with no code to fix gets spent searching. A small fake project works well, and keeps the cases out of your real repo. Build it into a gitignored `fixture/` before each run, with the packs you're testing installed the way a repo installs them. To test a pack you're editing, install it from your working tree by its absolute path:

```sh
rm -rf fixture && cp -R project fixture
mkdir -p fixture/context-packs/core
printf -- '---\nfrom: %s\npath: packs/core\n---\n' "$(cd .. && pwd)" > fixture/context-packs/core/pack.md
npx context-packs --dir fixture
```

An absolute `from` makes the table's rows absolute paths, which still resolve from the copy promptfoo makes for each run. A relative one wouldn't.

## Gotchas

- Without `setting_sources: ['project']`, the session loads no `CLAUDE.md`, so it never sees your tables.
- Run from a copy outside your folders, as `copy_working_dir` does. Claude Code also loads the `CLAUDE.md` of every folder above the one it runs in.
- promptfoo turns a list in `vars` into one case per item, which is why `reads` and `skips` are comma-separated strings.
- promptfoo finds the Agent SDK from the config's folder, so install both there.
