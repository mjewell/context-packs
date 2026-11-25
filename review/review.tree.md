# Review {#review}

A review checks a change against the repo's [[pack|packs]] and [[instruction-file|instruction file]], and reports [[findings]] for the change's author to decide.

- Rules are instructions to agents, kept in the [[instruction-file|instruction file]] and in [[pack|packs]] synced into it {#rules}
  - The instruction file is the `AGENTS.md` or `CLAUDE.md` a repo's agents read first {#instruction-file}
  - A pack is a collection of [[rules]] and [[doc|docs]], kept in a git repo or a folder, that a sync writes into the [[instruction-file|instruction file]] {#pack}
  - A doc is a file of [[rules]] that an agent reads only when its `when`, a line naming the work it applies to, matches the work {#doc}
- Each finding is a [[deviation]] from a [[rules|rule]], a [[conflict]] between two rules, or [[uncovered-choice|a choice no rule covers]]. It names its spots: the lines where it applies {#findings}
  - Deviation: the change goes against a written [[rules|rule]] {#deviation}
    - The change may be wrong, or the [[rules|rule]] may lack an exception or be out of date. The diff can't tell which, so the author decides
    - It says whether the [[rules|rule]]'s [[doc]] was routed, meaning its [[doc|when]] matches the work, since an unrouted rule may need its `when` fixed {#routed}
    - It gives any signs the [[deviation]] is deliberate
    - A [[findings|spot]] deviates when a careful reader would agree it breaks the [[rules|rule]]. A spot that could only be made better still follows it
      - Why: a [[rules|rule]] that calls for judgment, such as one on how text is written, can always be applied more strictly, and each run then found a new problem in the same lines
  - Conflict: two [[rules]] point opposite ways at the same [[findings|spot]] {#conflict}
    - The [[merge]] finds it, when the [[finders|finders']] answers hold [[rules]] that point opposite ways at the same [[findings|spots]]
    - It can't see one where the code follows one [[unit|unit's]] [[rules|rule]] and breaks another's, since a [[finders|finder]] reports only the rules a spot breaks. That reads as a [[deviation]]
      - Rejected: having the [[merge]] look for the opposing [[rules|rule]], since the agent would write rule text again, which its groups exist to prevent
    - The author decides which [[rules|rule]] wins
  - Uncovered choice: a kind of decision that will come up again, where another way would be reasonable and no [[rules|rule]] covers it {#uncovered-choice}
    - It shows how the existing code makes the choice, with two or three exemplars of each way
    - A second way beside an existing one is the strongest candidate, since an agent copies whichever way it reads first
    - Choices a linter, formatter or type check enforces are left out, and so is one-off logic
    - Only the strongest few are reported
      - Why: a missed choice turns up in a later review, while each weak candidate costs the author a turn
  - One choice is one [[findings|finding]], however many [[rules]] it breaks {#one-finding}
    - The [[findings|finding]] quotes each [[rules|rule]], and says whether each one's [[doc]] was [[routed]]
    - Why: kept apart, one import that two [[doc|docs]] forbid opened two [[review-threads|threads]] on the same line, and the second read as a new issue
  - Only the [[pack|packs]] and [[instruction-file|instruction file]] count. Bugs, and whether the change does what it set out to do, are for other kinds of code review
- Finder agents check the diff, one [[unit]] of [[doc|docs]] each, and a [[merge]] turns their answers into one list {#finders}
  - A unit is the [[doc|docs]] one [[finders|finder]] checks: the [[instruction-file|instruction file]], or the docs one [[pack]]'s table, its list of what to read for which work, points at. Each file is in exactly one unit {#unit}
    - The [[instruction-file|instruction file]] is the first [[unit]]. Its block is the part a sync writes. An inlined [[pack]] has its pack rules, the [[rules]] in its `pack.md`, written into the block {#inlined}
    - A nested [[pack]] that isn't [[inlined]] gets an index instead: a [[doc]] in its parent's [[unit]] that holds its [[inlined|pack rules]]
    - The [[unit|units]] come from `context-packs docs`, which reads the committed [[unit|tables]], not the [[pack|packs]], since a pack's origin can be a private repo CI can't read
      - Either way the CLI is fixed: CI runs it from the commit the caller pinned, and a [[local-review|local review]] runs the version released with the skill, since the newest on npm could be a bad publish
    - Why: splitting by [[pack]] would leave a [[finders|finder]] to pick an [[inlined]] pack's [[inlined|pack rules]] out of a file other packs share
  - The uncovered finder has no [[unit]]: it reads the whole diff for [[uncovered-choice|choices no rule covers]], and searches every unit's [[doc|docs]] for a [[rules|rule]] settling each {#uncovered-finder}
    - It runs alongside the [[unit|units']] [[finders]], so the [[merge]] doesn't have to read the diff for it afterwards
  - A [[finders|finder]] gets its [[doc|docs]]' names, not their text {#doc-names}
    - Why: with every [[doc]]'s text in the prompt, 5 of 5 runs read no doc and found nothing. They treated having the text as having checked it
    - Rejected: hooks that counted [[doc]] reads in Claude Code's transcripts. They tied the review to that format, and a crash in one passed the answer as if every doc was read
    - A [[local-review|local review]] checks that every doc was read, since its [[wizard]] prints each one itself
    - Rejected: checking in CI which [[doc|docs]] a [[finders|finder]] read, from its transcript. A run's log lists every tool call, so a skipped doc can be checked by hand
  - The merge groups the [[finders|finders']] findings, one group for each choice, see [[one-finding]], and each [[findings|finding]] is built from its group {#merge}
    - Each [[finders|finder's]] finding is numbered. A group gives the numbers it merges, with the [[findings|finding's]] kind, headline and take
    - The finding's [[rules]], [[findings|spots]], signs of deliberateness and exemplars all come from its group. A spot the group's findings disagree on deviates, since it goes against at least one [[rules|rule]]
      - Why: when the agent rewrote every [[findings|finding]], it could drop a [[rules|rule]] or a spot, and nothing noticed
    - Groups that leave out a [[finders|finder's]] finding, name one twice, or name one no finder reported stop the run
    - An [[uncovered-choice|uncovered choice]] joins a [[deviation]] about the same choice at the same [[findings|spots]], since a [[rules|rule]] covers it after all
  - A [[local-review|local review]] and a [[ci-review|CI review]] give their agents the same three prompt files, so both check the same way, with answers in the findings schema {#shared-prompts}
    - The [[wizard]] fills each one with the commands that read the [[doc|docs]] and the change, and how to hand in an answer, in a [[local-review|local review]] and in CI alike
    - The prompts, one each for a [[unit|unit's]] [[finders|finder]], the [[uncovered-finder|uncovered finder]] and the [[merge]], live with the schema in one folder, and every module reads them through one that owns the folder. The pack-findings skill links to neither
      - Why: when the skill linked to the schema outside its own folder, a local agent fetched it from a GitHub URL the user never pinned
  - The wizard runs every review, local or CI: a state machine that agents step through {#wizard}
    ```d2
    shape: sequence_diagram
    o: orchestrator
    w: wizard
    f: "finders, one per unit"
    m: merging agent
    o -> w: init
    w -> o: "start these finders, each with this prompt"
    o -> f: "Run `brief n`"
    f -> w: "brief n"
    w -> f: "prompt, doc commands, schema"
    f -> w: "doc, files, diff, log"
    f -> w: "submit n < answer file"
    w -> f: "taken, or what's missing"
    f -> o: "unit n is in"
    o -> w: next
    w -> o: "waiting on ..., or start the merge"
    o -> m: "Run `brief merge`"
    m -> w: "brief merge, sources"
    m -> w: "submit-groups < groups file"
    w -> m: findings built
    m -> o: done
    o -> w: next
    w -> o: "Done, with the findings"
    ```
    - The orchestrator, the agent that ran the skill, runs `init` and `next`, starts the subagents they name, and reads no [[doc]] or diff {#orchestrator}
      - It starts them in the foreground, and CI turns background subagents off. Why: a headless session ends with the orchestrator's turn, and a CI run whose finders started in the background ended before any answered
    - Each step does its deterministic work, keeps its state in a run folder, and prints the next step with every command in full {#run-folder}
      - No agent reads or writes the run folder. Agents reach it only through the wizard's commands, so the wizard decides what each one sees
      - `next` works from the run folder alone, so an [[orchestrator]] that lost its place picks the run back up
    - `init` and `next` tell the [[orchestrator]] what to do now {#next}
      ```d2
      direction: right
      finders: waiting on finders
      merge: waiting on the merge
      done: done
      finders -> merge: "every answer is in, with findings"
      finders -> done: "every answer is in, with none"
      merge -> done: "the groups are in"
      ```
      - `init` checks that the checkout is the head and the change touches a file. With `--head`, it lists [[rules|rule]] files with uncommitted changes. Then it names one [[finders|finder]] for each [[unit]] and the [[uncovered-finder|uncovered finder]], each with a one-line prompt
        - With `--uncommitted`, `init` reviews a commit it makes from the working files on top of `HEAD`, built in an index of its own, so the branch, the index and the files don't change. Untracked files are in it, ignored ones aren't
          - Finders still read rules and code from the checkout, so an edit during the review can reach them, as it can in a review of a commit
          - Rejected: a real commit, undone after. It runs the commit hooks, and undoing it loses which changes were staged
      - While answers are missing, `next` names each finder that hasn't answered, with its prompt, so one that stopped can be started again
      - Once every answer is in, `next` numbers the finders' findings and names the merging agent. Once its groups are in, `next` prints the [[findings]] and says who gets them: the skill that ran pack-findings, or else the user
        - When no finder found anything, `next` builds empty [[findings]] and prints them, since a merge would have nothing to group
      - Once the run is done, `finding <n>` prints one [[findings|finding]], with what its kind means and what the user decides about it
      - The run's state is which files its folder holds. The wizard works it out on each step instead of storing it, and refuses a step whose checks fail
        - A file whose existence is part of the state, such as an accepted answer or a phase's file, is written beside its name and then renamed, so a write cut short changes no state
        - Once the [[findings]] are built, `submit-groups` refuses any groups, so a done run never changes. `next` still prints its findings
    - A finder's brief is the wizard's prompt for its kind, with the commands that read its docs and the change, and its answer's schema {#brief}
      - `doc` prints one of the unit's docs and marks it served. `submit` takes a unit's answer only once every doc in it was served, and only in the schema's shape
        - Why: the wizard keeps its own record of what it printed, so the check needs no transcript, see [[doc-names]]
      - `submit` also refuses an answer whose spot names no line of its file at the head, or whose [[rules|rule]] names no file in the checkout, and says which finding and field
        - A spot may be outside the diff, since the report decides which spot a thread can open on
        - Rejected: checking that each quote is in its file. No run has misquoted a rule, and a finder that reformats one would be refused
      - `files`, `diff` and `log` read the change from the merge base, through fixed git commands, see [[change-commands]]. `diff` takes only a path the change touches
      - A refusal says what's missing and the command to run next. Once the [[merge]] starts, no finder's answer can change
    - The merging agent reads the numbered findings through `sources`, and `submit-groups` builds the [[findings]] from its groups, see [[merge]]
    - An agent writes each answer to the file its brief names, with its tool for writing files, then runs `submit`, which reads that file {#answers-folder}
      - The files are in an answers folder beside the [[run-folder|run folder]], not in it, so no agent can write what the wizard checked
      - Why: a scratchpad exists only for some accounts. A CI review's finders had none, so none of their answers could be written
      - Rejected: the answer in the command, such as in a heredoc. Claude Code refuses a command with a brace before a quote, which every JSON object starts with, even when it writes a file
      - The skill allows the wizard's command for the turn the finders start in. A headless run allows it at startup, and an interactive session asks about the [[orchestrator|orchestrator's]] later calls, and about each answer it writes outside the repo
    - Agents run each command exactly as printed, and the wizard takes only the arguments it names, spelled out
      - Why: Claude Code refused commands that wrapped one in a shell variable or a `cd`, and each refusal cost the agent a turn
      - Why: an allowed command prefix passes any arguments after it, and a shortened option would otherwise count as the full one
- In CI, four jobs find, pair and post the [[findings]], as [[review-threads|threads]] and one summary comment. Only the last can write to the PR {#ci-review}
  ```d2
  direction: right
  pr
  review
  pairing
  post: post {style.stroke-width: 3}
  pull: PR {shape: page}
  pr -> review: head and base
  review -> pairing
  review -> post: findings
  pairing -> post: pairs
  pull -> pairing: earlier threads
  post -> pull: writes
  ```
  - Why: each [[findings|finding]] needs a person to decide it, and a run in CI can't wait. So CI only reports, and nothing in it commits or pushes
  - The pr job reads the PR's head and base now, not from the event. It runs no agent {#pr-job}
    - Why: GitHub doesn't promise to queue runs in the order of their events, so the run left after cancellations can be an older one
    - Drafts, PRs from forks, and edits that don't change the base branch get no review {#review-trigger}
      - Why: a fork's PR gets no secrets. An edit reviews again only when it changed the base, so the [[findings]] match the new diff
    - A newer run cancels the one before it, through one concurrency group per PR {#run-cancel}
      - A run that won't review gets a group of its own, since GitHub cancels a run waiting in a group when another joins
      - A run cancelled during post leaves only comments it fully posted
  - The review job runs the pack-findings skill on the PR's range, as a [[local-review|local review]] does, and builds the report from the [[findings]] its [[wizard]] built {#review-job}
    - It can only read the repo, so GitHub, not the agent's tool list, keeps it from writing
    - It loads the skill from the review's checkout and asks for its checkout CLI, so every step runs the pinned code
      - Why: with the npm release the skill pins, a run between releases would pair one version's wizard with another's report
    - The report reads the one run that reached its findings, from a new temporary folder the job gave the agent. Any other count fails the job
      - Why: a review that didn't finish, or ran twice, would otherwise post findings nobody checked
      - Why: it never reads the agent's reply, since the wizard checked every answer behind the findings, and nothing checks the reply
    - The report refuses findings for a head other than the PR's
    - The run's log lists each tool call's input, and only whether its result was an error
      - Why: a call's full output can hold file contents and secrets
    - A [[findings|finding's]] anchor, the line its [[review-threads|thread]] opens on, is the first deviating [[findings|spot]] the diff shows, or else the first spot it shows, since a GitHub review comment needs a line in the diff {#anchor}
  - The pairing job does the [[pairing]] and writes the [[commentary]]
    - It reads the [[review-threads|threads]] through the [[trust-filter|trust filter]]
    - It checks out the PR though its agents read no files, since claude-code-action restores `.claude/` from the base branch with git
  - The post job opens new [[review-threads|threads]] and posts the [[ci-review|summary]]. It runs no agent {#post-job}
    - It reads the [[review-threads|threads]] again itself, through the [[trust-filter|trust filter]], and stops if a [[pairing|pair]] names any other thread
      - Why: the pairing job hands on only the pairs and commentary, and post needs each thread's state now: whether it's resolved, and whether the review's last reply is still the thread's last comment
      - Why: the pairs come from an agent's answer, and post is the one job that can write, so it checks them against a read of its own
    - It plans every write and checks the plan first. A PR that moved on, a [[ci-review|summary]] too long for a comment, or a second summary each stop it with nothing written
    - New [[review-threads|threads]] open in one GitHub review, submitted as it's created. Replies post one at a time
      - Why: a pending review left by a failed run would block the next, since GitHub allows one per user on a PR
    - Posts on one PR wait for each other rather than cancel
      - Why: two at once could each find no [[ci-review|summary]] and add one
    - It reads the PR's comments as one page of 100, and more is an error, since a [[ci-review|summary]] that missed an earlier one would post a second
  - GitHub enforces each job's permissions, and only the post job can write to the PR {#job-permissions}
    - Why: a composite action can't start a job or set its permissions, so the jobs live in a reusable workflow that a repo calls with one job
    - Each job checks out the review's code at the commit the caller pinned, so the actions and the workflow always match
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
    - The [[review-threads|thread]] opens with the [[findings|finding]] written for people: its headline, the [[rules]] it quotes, its other [[findings|spots]], signs it's deliberate, and the take: what the review would do about it, for the author to accept or overrule
    - It marks any [[rules|rule]] whose [[doc]] wasn't [[routed]], and for an [[uncovered-choice|uncovered choice]], says how the code makes it now
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
    wizard: wizard
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
  written.diff -> gates.wizard
  gates.wizard -> agents.finder
  gates.wizard -> agents.merger
  own -> agents.pairer
  agents -> out
  out -> pr: post only
  ```
  - A CI agent's shell runs only the skill's commands, each allowed as a prefix: the [[wizard|wizard's]], `git rev-parse` and `git status` {#allowed-commands}
    - An allowed prefix refused redirects, command substitution, env prefixes and chained commands after it, but let options through, so the wizard takes only the options it names
    - `git rev-parse` and `git status` have no option that writes a file
      - Rejected: other git commands. Claude Code doesn't check what a shell command writes, and an allowed `git log` wrote any text to any file through `--output`
    - It reads files with Read, Glob and Grep, confined to the checkout, and writes only in the [[answers-folder|answers folder]], which the job makes before the agent starts. Read is denied on `.git/`, where claude-code-action keeps its token
      - Why: a headless run writes outside its working directory only with both `--add-dir` and an `Edit` rule for the folder. Either alone was refused
  - Agents read the change through the wizard, which runs one fixed git command for each of `files`, `diff` and `log` {#change-commands}
    - The agent sends a path and a page number, never a revision. A path must be one the change touches, and is taken literally, so `*` names only a file called `*`
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
- The author goes through the [[findings]] locally, decides each one, and records the [[rules]] they want {#local-review}
  - The author runs /pack-review on a PR, which reads CI's [[findings]] or runs the pack-findings skill {#pack-review}
    - [[findings|Findings]] come from the first source that has them: a [[wizard]] run in this conversation, CI's [[ci-review|summary]], then a fresh run of pack-findings
      - pack-findings shows nothing and hands back its [[wizard|wizard's]] `next` command. [[pack-review]] runs it and shows each [[findings|finding]], so the author sees each one once
        - Why: after a compaction, the conversation holds only a summary of the [[findings]], while `next` prints the ones the wizard checked
    - It loads pack-findings with the Skill tool, which can't load a skill that sets `disable-model-invocation`, so pack-findings is the one skill that doesn't
  - CI's [[ci-review|summary]] carries every [[findings|finding]] as JSON, so the author works through exactly what CI found {#summary-json}
    - Rejected: a CI artifact. It would expire, and reviewing again locally costs a second review that could find different things
    - The [[ci-review|summary]] holds at most 65,536 characters, GitHub's limit for a comment. A summary that doesn't fit stops the run
  - It summarizes every [[findings|finding]], then goes through them one at a time, waiting for the author's decision on each
    - A [[findings|finding's]] [[commentary]] is shown as CI's reading of the [[review-threads|thread]], for the author to check there
    - [[pack-review]] stays in chat, and posts to the PR only when the author asks
  - A [[deviation]] is fixed in the code or in the [[rules|rule]]. A [[conflict]] needs a winner. An [[uncovered-choice|uncovered choice]] is written down or left
  - pack-rule writes one [[rules|rule]] for each [[findings|finding]] the author wants recorded, and waits for the wording to be approved
    - It gets the [[findings|finding's]] kind, whether its [[doc]] was [[routed]], its [[rules]] and [[findings|spots]], any signs it's deliberate, and the author's answer
  - The [[findings]] are stale when the PR's head or base branch has moved. The author then picks whether to go on {#stale-summary}
    - Why: the base commit moves whenever something merges into the base branch, while the diff from the merge base stays the same
    - A force push to the base branch can change the diff without either moving, and goes unnoticed
  - The checkout must be the head CI reviewed, since the [[findings|findings']] [[findings|spots]] and the [[pack]] edits are read there
