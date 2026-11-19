# Review {#review}

A review checks a change against the repo's packs and instruction file, and reports findings for the change's author to decide.

- Each finding is a deviation from a rule, a conflict between two rules, or a choice no rule covers {#findings}
  - Deviation: the change goes against a written rule {#deviation}
    - The change may be wrong, or the rule may lack an exception or be out of date. The diff can't tell which, so the author decides
    - It says whether the rule's doc was routed, meaning its `when` matches the work, since an unrouted rule may need its `when` fixed
    - It gives any signs the deviation is deliberate
  - Conflict: two rules point opposite ways at the same spot {#conflict}
    - The merge finds it, when the finders' answers hold rules that point opposite ways at the same spots
    - The author decides which rule wins
  - Uncovered choice: a kind of decision that will come up again, where another way would be reasonable and no rule covers it {#uncovered-choice}
    - It shows how the existing code makes the choice, with two or three exemplars of each way
    - A second way beside an existing one is the strongest candidate, since an agent copies whichever way it reads first
    - Choices a linter, formatter or type check enforces are left out, and so is one-off logic
    - Only the strongest few are reported
      - Why: a missed choice turns up in a later review, while each weak candidate costs the author a turn
  - One choice is one finding, however many rules it breaks {#one-finding}
    - The finding quotes each rule, and says whether each one's doc was routed
    - Why: kept apart, one import that two docs forbid opened two threads on the same line, and the second read as a new issue
  - Only the packs and instruction file count. Bugs, and whether the change does what it set out to do, are for other reviews
- Finder agents check the diff, one unit of docs each, and a merge turns their answers into one list {#finders}
  - A unit is the docs one finder checks: the instruction file, or the docs one pack's table points at. Each file is in exactly one unit {#unit}
    - The instruction file is the first unit. It holds the pack rules of every pack inlined in the block
    - A nested pack's index is a doc in its parent's unit, and holds that pack's pack rules
    - The units come from `context-packs docs`, which reads the committed tables, not the packs, since a pack's origin can be a private repo CI can't read
    - Why: splitting by pack would leave a finder to pick an inlined pack's rules out of a file other packs share
  - The uncovered finder has no unit. It reads the whole diff for choices no rule covers, and searches every unit's docs for a rule that settles each {#uncovered-finder}
    - It runs alongside the units' finders, so the merge doesn't have to read the diff for it afterwards
  - A finder gets its docs' names, not their text {#doc-names}
    - Why: with every doc's text in the prompt, 5 of 5 runs read no doc and found nothing. They treated having the text as having checked it
    - Rejected: hooks that counted doc reads in Claude Code's transcripts. They tied the review to that format, and a crash in one passed the answer as if every doc was read
    - Rejected: checking which docs a finder read. A run's log lists every tool call, so a skipped doc can be checked by hand
  - The merge writes one finding for each choice, see [[one-finding]] {#merge}
    - An uncovered choice joins a deviation about the same choice at the same spots, since a rule covers it after all
  - A local review and a CI review give their agents the same three prompt files, so both check the same way {#shared-prompts}
    - Locally, one agent launches a subagent per unit, all at once, and reads no doc itself
    - In CI, the workflow starts the finders. Each prompt gains only what a CI agent needs: that it has no shell, and to copy line numbers from the diff
- In CI, five jobs find, merge and post the findings, and only the last can write to the PR {#ci-review}
  ```d2
  direction: right
  units
  find: find {style.multiple: true}
  merge
  threads
  post: post {style.stroke-width: 3}
  pr: PR {shape: page}
  units -> find: one per unit
  find -> merge -> threads -> post
  merge -> post
  pr -> threads: earlier threads
  post -> pr: writes
  ```
  - More: [ci-review](ci-review/ci-review.md)
- Across pushes, each finding lands in the review thread already open for its issue {#review-threads}
  - Pairing decides which finding is about the same issue as which of pack-review's threads {#pairing}
    - It's done by an agent
      - Why: an agent can judge that a finding and a thread are about the same issue when their wording differs
    - The agent sees only this run's findings and the comment each thread opened with, never a reply
      - Why: no comment can move a finding to another thread, by mistake or on purpose
    - A check refuses a pair that names no finding, a thread that isn't pack-review's, or either one twice
    - The agent's only tool returns its structured answer. With no tools at all, it answers in text, which fails the step
  - A new finding opens a thread on its anchor. A finding with no line in the diff appears in the summary only {#new-thread}
    - The thread opens with the finding written for people: its headline, the rules it quotes, its other spots, signs it's deliberate, and the take
    - It marks any rule whose doc wasn't routed, and for an uncovered choice, says how the code makes it now
    - The thread holds no JSON, since the next run's pairing agent reads the same text
  - A paired finding gets a reply only with commentary, or when its thread was resolved, so running the review again stays quiet
    - A resolved thread hears that its finding is still there once, and not again while that reply is the thread's last comment
    - A thread with no finding gets nothing, since the author decides whether a thread is resolved
  - Commentary comes from a second agent, after the pairs are fixed, and only when a reply gives the author a reason to act {#commentary}
    - It sees every paired thread as the trust filter passes it, not only ones with a new reply
      - Why: an author who pushed a fix without saying so still hears when it didn't work
    - Its own earlier comments are labelled as its own, and replies after its last comment are marked as new
      - Why: labelled by the bot's login instead, it relayed the same reply on every push
    - A check refuses commentary on an unpaired finding, two entries for one finding, or an empty one
  - The review never resolves a thread. The author does
    - Why: the workflow's token can't, and a token that could can also push
  - pack-review's comments are told apart by the token's identity and a marker together {#comment-identity}
    - Why: other workflows post with the same token, and anyone can type the marker
    - The marker goes at the end of the summary, after the JSON block, so the agent's text can't put it there
- Text anyone can write reaches an agent only filtered, and no agent can write to the PR {#untrusted-text}
  ```d2
  direction: right
  written: anyone can write {
    diff: diff and files
    replies: replies
  }
  own: pack-review's\nown comments
  gates: only through {
    style.stroke-dash: 3
    trust: trust filter
    read: read the checkout
    git: git server
  }
  agents: agents {
    pairer: pairing {shape: hexagon}
    commenter: commentary {shape: hexagon}
    finder: finders {shape: hexagon}
    merger: merging {shape: hexagon}
  }
  out: sanitize
  pr: PR {shape: page}
  written.replies -> gates.trust -> agents.commenter
  written.diff -> gates.read -> agents.finder
  written.diff -> gates.git
  gates.git -> agents.finder
  gates.git -> agents.merger
  own -> agents.pairer
  agents -> out
  out -> pr: post only
  ```
  - More: [untrusted-text](untrusted-text/untrusted-text.md)
- The author goes through the findings locally, decides each one, and records the rules they want {#local-review}
  - The author runs /pack-review on a PR, which reads CI's findings or finds them itself {#pack-review}
    - Findings come from the first source that has them: this conversation, CI's summary, then a fresh run of pack-findings
    - It loads pack-findings with the Skill tool, which can't load a skill that sets `disable-model-invocation`, so pack-findings is the one skill that doesn't
  - CI's summary carries every finding as JSON, so the author works through exactly what CI found {#summary-json}
    - Rejected: a CI artifact. It would expire, and reviewing again locally costs a second review that could find different things
    - The summary holds at most 65,536 characters, GitHub's limit for a comment. A summary that doesn't fit stops the run
  - It summarizes every finding, then goes through them one at a time, waiting for the author's decision on each
    - A finding's commentary is shown as CI's reading of the thread, for the author to check there
    - The review stays in chat. It posts to the PR only when the author asks
  - A deviation is fixed in the code or in the rule. A conflict needs a winner. An uncovered choice is written down or left
  - pack-rule writes one rule for each finding the author wants recorded, and waits for the wording to be approved
    - It gets the finding's kind, whether its doc was routed, its rules and spots, any signs it's deliberate, and the author's answer
  - The findings are stale when the PR's head or base branch has moved. The author then picks whether to go on {#stale-summary}
    - Why: the base commit moves whenever something merges into the base branch, while the diff from the merge base stays the same
    - A force push to the base branch can change the diff without either moving, and goes unnoticed
  - The checkout must be the head CI reviewed, since the findings' spots and the pack edits are read there
