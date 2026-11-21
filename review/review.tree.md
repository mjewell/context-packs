# Review {#review}

A review checks a change against the repo's packs and instruction file, and reports [[findings]] for the change's author to decide.

- Each finding is a [[deviation]] from a rule, a [[conflict]] between two rules, or [[uncovered-choice|a choice no rule covers]]. It names its spots: the lines where it applies {#findings}
  - Deviation: the change goes against a written rule {#deviation}
    - The change may be wrong, or the rule may lack an exception or be out of date. The diff can't tell which, so the author decides
    - It says whether the rule's doc was routed, meaning its `when` matches the work, since an unrouted rule may need its `when` fixed {#routed}
    - It gives any signs the [[deviation]] is deliberate
  - Conflict: two rules point opposite ways at the same [[findings|spot]] {#conflict}
    - The [[merge]] finds it, when the [[finders|finders']] answers hold rules that point opposite ways at the same [[findings|spots]]
    - The author decides which rule wins
  - Uncovered choice: a kind of decision that will come up again, where another way would be reasonable and no rule covers it {#uncovered-choice}
    - It shows how the existing code makes the choice, with two or three exemplars of each way
    - A second way beside an existing one is the strongest candidate, since an agent copies whichever way it reads first
    - Choices a linter, formatter or type check enforces are left out, and so is one-off logic
    - Only the strongest few are reported
      - Why: a missed choice turns up in a later review, while each weak candidate costs the author a turn
  - One choice is one [[findings|finding]], however many rules it breaks {#one-finding}
    - The [[findings|finding]] quotes each rule, and says whether each one's doc was [[routed]]
    - Why: kept apart, one import that two docs forbid opened two [[review-threads|threads]] on the same line, and the second read as a new issue
  - Only the packs and instruction file count. Bugs, and whether the change does what it set out to do, are for other reviews
- Finder agents check the diff, one [[unit]] of docs each, and a [[merge]] turns their answers into one list {#finders}
  - A unit is the docs one [[finders|finder]] checks: the instruction file, or the docs one pack's table points at. Each file is in exactly one unit {#unit}
    - The instruction file is the first [[unit]]. It holds the pack rules of every pack inlined in the block
    - A nested pack's index is a doc in its parent's [[unit]], and holds that pack's pack rules
    - The [[unit|units]] come from `context-packs docs`, which reads the committed tables, not the packs, since a pack's origin can be a private repo CI can't read
      - Either way the CLI is fixed: CI runs it from the commit the caller pinned, and a [[local-review|local review]] runs the version released with the skill, since the newest on npm could be a bad publish
    - Why: splitting by pack would leave a [[finders|finder]] to pick an inlined pack's rules out of a file other packs share
  - The uncovered finder has no [[unit]]. It reads the whole diff for [[uncovered-choice|choices no rule covers]], and searches every unit's docs for a rule that settles each {#uncovered-finder}
    - It runs alongside the [[unit|units']] [[finders]], so the [[merge]] doesn't have to read the diff for it afterwards
  - A [[finders|finder]] gets its docs' names, not their text {#doc-names}
    - Why: with every doc's text in the prompt, 5 of 5 runs read no doc and found nothing. They treated having the text as having checked it
    - Rejected: hooks that counted doc reads in Claude Code's transcripts. They tied the review to that format, and a crash in one passed the answer as if every doc was read
    - Rejected: checking which docs a [[finders|finder]] read. A run's log lists every tool call, so a skipped doc can be checked by hand
  - The merge writes one [[findings|finding]] for each choice, see [[one-finding]] {#merge}
    - An [[uncovered-choice|uncovered choice]] joins a [[deviation]] about the same choice at the same [[findings|spots]], since a rule covers it after all
  - A [[local-review|local review]] and a [[ci-review|CI review]] give their agents the same three prompt files and findings schema, so both check the same way and hand back the same shape {#shared-prompts}
    - Locally, one agent launches a subagent per [[unit]], all at once, and reads no doc itself
    - In CI, the workflow starts the [[finders]]. Each prompt gains only what a CI agent needs: that it has no shell, and to copy line numbers from the diff
    - The prompts, one each for a [[unit|unit's]] finder, the [[uncovered-finder|uncovered finder]] and the [[merge]], live with the schema in the pack-findings skill's folder, since an installed skill holds only its own folder
      - Why: with the schema in `review/`, a local agent fetched it from a GitHub URL the user never pinned
- In CI, five jobs find, merge and post the [[findings]], as [[review-threads|threads]] and one summary comment. Only the last can write to the PR {#ci-review}
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
  - Why: each [[findings|finding]] needs a person to decide it, and a run in CI can't wait. So CI only reports, and nothing in it commits or pushes
  - The units job lists the [[unit|units]], and reads the PR's head and base now, not from the event {#units-job}
    - Why: GitHub doesn't promise to queue runs in the order of their events, so the run left after cancellations can be an older one
    - Drafts, PRs from forks, and edits that don't change the base branch get no review {#review-trigger}
      - Why: a fork's PR gets no secrets. An edit reviews again only when it changed the base, so the [[findings]] match the new diff
    - A newer run cancels the one before it, through one concurrency group per PR {#run-cancel}
      - A run that won't review gets a group of its own, since GitHub cancels a run waiting in a group when another joins
      - A run cancelled during post leaves only comments it fully posted
  - The find job runs one [[finders|finder]] per [[unit]], started by the workflow, so no agent decides a unit isn't worth checking {#find-job}
    - Why: an agent left to decide skipped [[unit|units]] on small diffs
    - It can only read the repo, so GitHub, not the agent's tool list, keeps it from writing
    - It reads the change through the [[git-server|git server]]
    - The run's log lists each tool call's input, and only whether its result was an error
      - Why: a call's full output can hold file contents and secrets
  - The merge job merges the [[finders|finders']] answers, then a script picks the line in the diff each [[findings|finding's]] [[review-threads|thread]] opens on {#merge-job}
    - claude-code-action checks the merging agent's answer against the findings schema
    - A [[findings|finding's]] anchor, the line its [[review-threads|thread]] opens on, is the first deviating [[findings|spot]] the diff shows, or else the first spot it shows, since a review comment needs a line in the diff {#anchor}
  - The threads job does the [[pairing]] and writes the [[commentary]]
    - It checks out the PR though its agents read no files, since claude-code-action restores `.claude/` from the base branch with git
  - The post job opens new [[review-threads|threads]] and posts the [[ci-review|summary]]. It runs no agent {#post-job}
    - It reads the [[review-threads|threads]] again itself, through the [[trust-filter|trust filter]], and stops if a [[pairing|pair]] names any other thread
    - It plans every write and checks the plan first. A PR that moved on, a [[ci-review|summary]] too long for a comment, or a second summary each stop it with nothing written
    - New [[review-threads|threads]] open in one GitHub review, submitted as it's created. Replies post one at a time
      - Why: a pending review left by a failed run would block the next, since GitHub allows one per user on a PR
    - Posts on one PR wait for each other rather than cancel
      - Why: two at once could each find no [[ci-review|summary]] and add one
    - It reads the PR's comments as one page of 100, and more is an error, since a [[ci-review|summary]] that missed an earlier one would post a second
  - GitHub enforces each job's permissions, and only the post job can write to the PR {#job-permissions}
    - Why: a composite action can't start a job or set its permissions, so the jobs live in a reusable workflow that a repo calls with one job
    - Each job checks out the review at the commit the caller pinned, so the actions and the workflow always match
    - The jobs hand their results on as artifacts, kept for one day
    - It needs GitHub.com, since GitHub Enterprise Server doesn't give a job the pinned commit
    - claude-code-action is pinned by commit, since the review relies on how it passes arguments, the prompt and the token
- Across pushes, each [[findings|finding]] lands in the review thread already open for its issue {#review-threads}
  - Pairing decides which [[findings|finding]] is about the same issue as which open [[review-threads|review thread]] {#pairing}
    - It's done by an agent
      - Why: an agent can judge that a [[findings|finding]] and a [[review-threads|thread]] are about the same issue when their wording differs
    - The agent sees only this run's [[findings]] and the comment each [[review-threads|thread]] opened with, never a reply
      - Why: no comment can move a [[findings|finding]] to another [[review-threads|thread]], by mistake or on purpose
    - A check refuses a [[pairing|pair]] that names no [[findings|finding]], a [[review-threads|thread]] the [[ci-review|CI review]] didn't open, or either one twice
    - The agent's only tool returns its structured answer. With no tools at all, it answers in text, which fails the step
  - A new [[findings|finding]] opens a [[review-threads|thread]] on its [[anchor]]. A finding with no line in the diff appears in the [[ci-review|summary]] only {#new-thread}
    - The [[review-threads|thread]] opens with the [[findings|finding]] written for people: its headline, the rules it quotes, its other [[findings|spots]], signs it's deliberate, and the take: what the review would do about it, for the author to accept or overrule
    - It marks any rule whose doc wasn't [[routed]], and for an [[uncovered-choice|uncovered choice]], says how the code makes it now
    - The [[review-threads|thread]] holds no JSON, since the next run's [[pairing]] agent reads the same text
  - A [[pairing|paired]] [[findings|finding]] gets a reply only with [[commentary]], or when its [[review-threads|thread]] was resolved, so running the review again stays quiet
    - A resolved [[review-threads|thread]] hears that its [[findings|finding]] is still there once, and not again while that reply is the thread's last comment
    - A [[review-threads|thread]] with no [[findings|finding]] gets nothing, since the author decides whether a thread is resolved
  - Commentary comes from a second agent, after the [[pairing|pairs]] are fixed, and only when a reply gives the author a reason to act {#commentary}
    - It sees every [[pairing|paired]] [[review-threads|thread]] as the [[trust-filter|trust filter]] passes it, not only ones with a new reply
      - Why: an author who pushed a fix without saying so still hears when it didn't work
    - Its own earlier comments are labelled as its own, and replies after its last comment are marked as new
      - Why: labelled by the bot's login instead, it relayed the same reply on every push
    - A check refuses [[commentary]] on an [[pairing|unpaired]] [[findings|finding]], two entries for one finding, or an empty one
  - The review never resolves a [[review-threads|thread]]. The author does
    - Why: the workflow's token can't, and a token that could can also push
  - The [[ci-review|CI review's]] comments are told apart by the token's identity together with a marker, the HTML comment `<!-- pack-review -->` {#marker}
    - Why: other workflows post with the same token, and anyone can type the [[marker]]
    - The [[marker]] goes at the end of the [[ci-review|summary]], after the JSON block, so the agent's text can't put it there
- Text anyone can write reaches an agent only filtered, and no agent can write to the PR {#untrusted-text}
  ```d2
  direction: right
  written: anyone can write {
    diff: diff and files
    replies: replies
  }
  own: the review's\nown comments
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
  - Agents have no shell. They read files with Read, Glob and Grep, confined to the checkout {#no-shell}
    - The merging agent can also read the folder holding the [[finders|finders']] answers
    - Read is denied on `.git/`, where claude-code-action keeps its token
    - Rejected: allowing git commands in a shell. Claude Code doesn't check what a shell command writes, and an allowed `git log` wrote any text to any file
  - They read the change through a git server, whose three tools each run one fixed git command {#git-server}
    - The tools are changed, diff and log. The agent sends a path and a page number, never a revision
    - A path must be relative and without `..`, and is taken literally, so `*` names only a file called `*`
    - Diffs run without external diff drivers or text conversion, since a PR picks a path's diff driver
    - Output comes in pages of 1,000 lines, so one call can't fill the agent's context
    - Each diff line the head has starts with its line number there
      - Why: reading the diff as one file, the agent gave line numbers past the end of the files they named
  - The trust filter passes a reply to an agent only when its author can write to the repo now, or the review wrote it {#trust-filter}
    - Anyone else's reply comes back as its id and why it's hidden, without the login, since a login is text its owner chose
    - Write access comes from GitHub's permission API, asked once per author
    - A minimized comment isn't hidden. It comes with GitHub's reason, for the [[commentary]] agent to weigh
    - Reply text is GitHub's plain-text rendering, so GitHub decides what's hidden, such as HTML comments
    - Rejected: GitHub's lockdown mode. It does nothing on private repos, filters only some comments, and doesn't strip hidden content
  - [[findings|Findings]] lose invisible characters and secrets before they're posted, and their mentions and HTML are escaped {#sanitize}
    - Every Unicode format character is removed, not a list of known ones. Secrets are redacted by prefix
    - Each @ before a login gets an invisible word joiner, so no one is notified
    - `<` is escaped, so no HTML comment or tag can hide text. Links and images still render
    - Rejected: backticks around mentions, since the agent's own backticks can pair with them and leave the mention outside
  - The [[local-review|local review]] reads only the [[ci-review|summary]], through one command that prints no other comment's text {#summary-read}
    - The filter runs before the agent sees any comment, since other comments can hold text written to steer it
    - It reads every page, so a [[ci-review|summary]] or a forged block past the first page isn't missed
    - It reads the [[ci-review|summary's]] plain-text rendering, which leaves out HTML comments, image alt text and link URLs
    - A [[ci-review|summary]] counts only when the workflow's bot wrote it, it ends with the [[marker]], and it holds one findings block
  - Every prompt, and both the pack-findings and [[pack-review]] skills, tell their agent that what it reads is data, never instructions
  - Text from the PR reaches a step output only under a delimiter it can't contain, so a line in it can't set another output
- The author goes through the [[findings]] locally, decides each one, and records the rules they want {#local-review}
  - The author runs /pack-review on a PR, which reads CI's [[findings]] or runs the pack-findings skill {#pack-review}
    - [[findings|Findings]] come from the first source that has them: this conversation, CI's [[ci-review|summary]], then a fresh run of pack-findings
      - A fresh run hands its [[findings]] back unshown, and [[pack-review]] shows each one, so the author doesn't see it twice
    - It loads pack-findings with the Skill tool, which can't load a skill that sets `disable-model-invocation`, so pack-findings is the one skill that doesn't
  - CI's [[ci-review|summary]] carries every [[findings|finding]] as JSON, so the author works through exactly what CI found {#summary-json}
    - Rejected: a CI artifact. It would expire, and reviewing again locally costs a second review that could find different things
    - The [[ci-review|summary]] holds at most 65,536 characters, GitHub's limit for a comment. A summary that doesn't fit stops the run
  - It summarizes every [[findings|finding]], then goes through them one at a time, waiting for the author's decision on each
    - A [[findings|finding's]] [[commentary]] is shown as CI's reading of the [[review-threads|thread]], for the author to check there
    - The review stays in chat. It posts to the PR only when the author asks
  - A [[deviation]] is fixed in the code or in the rule. A [[conflict]] needs a winner. An [[uncovered-choice|uncovered choice]] is written down or left
  - pack-rule writes one rule for each [[findings|finding]] the author wants recorded, and waits for the wording to be approved
    - It gets the [[findings|finding's]] kind, whether its doc was [[routed]], its rules and [[findings|spots]], any signs it's deliberate, and the author's answer
  - The [[findings]] are stale when the PR's head or base branch has moved. The author then picks whether to go on {#stale-summary}
    - Why: the base commit moves whenever something merges into the base branch, while the diff from the merge base stays the same
    - A force push to the base branch can change the diff without either moving, and goes unnoticed
  - The checkout must be the head CI reviewed, since the [[findings|findings']] [[findings|spots]] and the pack edits are read there
