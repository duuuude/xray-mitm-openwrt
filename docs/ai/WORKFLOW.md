# AI Workflow

This document explains how the project owner and AI Works operate the project
without accumulating duplicate implementation contexts.

## Recommended number of active Works

Keep exactly **3 normal persistent Works**:

```text
1. Development Lead — Owner Console
2. PR Reviewer
3. Router & Release Validation
```

The Development Lead performs normal implementation. Do not create a separate
Implementation Work for every PR. A temporary specialist Work is appropriate
only when a concrete task needs separate context or isolation.

The reusable agent roles in `PROMPTS.md` are **prompt templates**, not permanent Works.

For example, “Release Agent”, “Git Audit Agent”, and “Compatibility Agent” are roles you invoke when needed. They do not each need a permanent Work.

---

## What each persistent Work does

### Development Lead — Owner Console

Persistent.

It is the single project control tower and combines:

```text
project coordination
normal implementation
roadmap maintenance
routine Git/worktree operations
Owner Gatekeeper
GitHub issue and community triage
```

It may select one approved PR, define scope, implement the smallest coherent
change, run validation, commit, and normally fast-forward push the approved
feature branch. It may evaluate reviewer findings and implement accepted
ordinary corrections.

It must never independently approve its own implementation for merge. Every
merge candidate returns to the independent PR Reviewer after implementation
and after accepted corrections.

### PR Reviewer

Persistent and independent.

Use it to:

```text
review the current feature branch against main
search for regressions
check safety invariants
check scope creep
identify missing tests
```

It reports evidence and findings back to Development Lead — Owner Console. It
does not modify the implementation, route follow-up work, or approve an owner-
gated action.

### Router & Release Validation

Persistent and independent.

Use it for:

```text
AX4200 validation
LuCI browser testing
real-service testing
release preflight
release evidence
```

Use it only when real OpenWrt, AX4200, browser, runtime, release, rollback,
certificate, PassWall2, or similar evidence is required. It reports back to
Development Lead — Owner Console and does not route another Work.

Router mutations and protected signing/release actions remain owner-gated.

---

## Temporary specialist Works

Reusable roles in `PROMPTS.md`, including Implementation, Release,
Compatibility, Verification, and Git Audit, are specialist templates rather
than normal persistent Works. Create a temporary specialist Work only when the
task has a concrete need for separate context or isolation. Its report returns
to Development Lead — Owner Console; it must not select or prompt the next
Work.

---

## Normal cycle

```text
Development Lead
    ↓
select one approved PR
define scope and acceptance criteria
create branch/worktree
implement + validate + normal feature-branch push
    ↓
complete self-contained handoff

PR Reviewer
    ↓
independent evidence + findings
return to Development Lead
    ↓

Development Lead
    ↓
evaluate findings
implement accepted corrections only
return for independent review as needed
    ↓

Automated validation / CI
    ↓

Router & Release Validation
    ↓
only if required
return to Development Lead
    ↓

owner gate for merge or another high-risk action
    ↓

owner-approved merge
    ↓

confirm merge state
check dirty files
check untracked files
confirm no unique work would be lost
    ↓

remove worktree only when clean and unambiguous
    ↓

Development Lead updates MASTER_PLAN.md
```

If any check fails, stop and do not remove a dirty or ambiguous worktree
automatically. See `AGENTS.md`.

---

## Staged autonomous PR initiative

`docs/ai/AUTONOMOUS_PR.md` records the owner's current workflow priority:
reduce manual message transport for one approved, low-risk PR while preserving
the three independent Works and all owner gates. Each stage is a separate PR;
Stage 0 changes documentation only. Stage 3 must prove a qualifying
zero-additional-spend, subscription-authenticated scriptable runtime before
any unattended controller is built. A semi-autonomous three-Work process
remains the fallback if that pilot fails.

Normal PR creation and CI are routine, reversible steps; the owner decision
is whether to merge after current-candidate independent review, required CI,
and any conditional real-system gate. Review may precede PR creation, but it
must be repeated when the candidate changes. Neither an AI review nor CI
alone replaces the owner merge decision.

---

## Routine actions and owner gates

Development Lead may handle routine, reversible work without interrupting the
owner:

```text
choose the next approved PR
create a normal feature branch/worktree
edit inside approved scope
run non-destructive tests
make local commits
normally fast-forward push the approved feature branch
request independent review
implement accepted ordinary review corrections
update documentation inside approved scope
```

A normal feature-branch push is routine only when the branch is the approved
current PR branch, implementation stayed in scope, required validation ran or
skipped checks were reported, no unexpected files are present, and the push is
a non-force fast-forward push to a branch other than `main`.

Development Lead must stop for owner approval before:

```text
merge to main
tag or release
production signing-material operations
live router routing, firewall, DNS, CA/certificate, PassWall2, reboot, reset,
or restore mutations
force-push or shared-history rewrite
deleting a branch with unique work
removing a dirty or ambiguous worktree
deleting backups or user data
materially expanding approved PR scope
changing product, security, or support policy
accepting a significant architectural or security tradeoff
overriding a BLOCK or HIGH-severity safety finding
acting when rollback is unclear or material evidence is missing
```

---

## Handoff and routing protocol

Development Lead is the only routing layer. When another Work returns a
report, the Lead decides the next project action and produces a complete,
copy-ready handoff. The owner must not have to assemble prompts, copy findings,
infer Git permissions, decide manual gates, or select the next Work.

Normal handoffs use exactly:

```text
Next Work:
<exact Work name>

Owner action before handoff:
YES or NO

Owner action:
<only when YES; exact decision or MAC command>

Complete message to send:
<fully self-contained copy-ready message>

Why this is next:
<brief reason>
```

The complete message includes the repository, branch, head and base when
relevant, exact scope, accepted findings, acceptance criteria, validation and
skipped checks, manual OpenWrt/AX4200/browser gates, Git and push permissions,
and stop condition.

When an owner gate is reached, Development Lead asks for the exact decision
before routing or performing the gated action, using:

```text
OWNER DECISION REQUIRED

Decision:
<exact decision>

Why my approval is required:
<brief explanation>

Recommended option:
<recommendation>

Alternatives:
<only meaningful alternatives>

Risk if approved:
<brief>

Risk if declined:
<brief>

Exact action after approval:
<complete handoff or MAC command>
```

PR Reviewer and Router & Release Validation must deliver their complete
evidence and recommendation explicitly to the Development Lead task using the
host's task/thread handoff mechanism. Every handoff request must carry the
recipient's exact task/thread ID; the role title alone is not a routable
destination. Development Lead includes this field in the request:

```text
Lead task thread ID: <exact Development Lead task/thread ID>
```

Before finalizing, each non-Lead Work must:

1. Call `send_message_to_thread` using the exact recipient and the entire
   completed report (including evidence, limits, and recommendation):

   ```javascript
   send_message_to_thread({
     threadId: "<exact Lead task thread ID>",
     prompt: "<complete report>"
   })
   ```

   A task title or a statement such as “report delivered” is not a substitute
   for this call.
2. Confirm the tool returned success for the expected thread ID. Include a
   short delivery receipt in the final response, and include the complete
   report there as well when the host permits it.
3. If the call fails or the destination cannot be confirmed, state exactly
   `HANDOFF DELIVERY FAILED`; do not claim the handoff succeeded.

They do not choose, authorize, or prompt the next Work. Development Lead
checks that the complete report—not just a status or summary—is visible in the
Lead task before relying on the recommendation. A Work's completed or idle
status, successful CI, or a send attempt without a matching successful tool
result is not a delivered report or approval. If the report is absent, Lead
re-requests it directly using the exact source and destination task IDs. Until
the complete report arrives, record the review as `UNPROVEN / NOT DELIVERED`,
do not say the PR is merge-ready, and never ask the owner to copy or relay it.
If the retry also fails, record `HANDOFF DELIVERY FAILED`, keep the gate
blocked, and use the persistent Reviewer Work to regenerate/deliver the report
from its evidence; do not infer a clean review from status alone.

---

## GitHub issue and community triage

Development Lead handles ordinary issue triage without creating an
implementation task. It first inspects the actual issue and current `main`,
documentation, and relevant code, then classifies the report as support or
question, confirmed bug, likely bug needing reproduction, documentation
problem, feature or compatibility request, or unsupported configuration.

Support questions and clarifications may be answered directly. Bug replies
separate known facts from unproven behavior and request only the minimum useful
non-secret diagnostics. Feature and compatibility replies describe current
support without promising implementation or timing.

Filing an issue does not authorize implementation. Adding or prioritizing new
roadmap work, or changing product, security, or support policy, remains an
owner decision unless already approved.

---

## What can be automated

A large part of the engineering workflow can be automated.

### Good automation targets

```text
check repo/remotes/upstream
create feature branch/worktree
run focused tests
run full validation
run git diff --check
check changed-file categories
decide whether router/browser testing is required
run GitHub Actions
build packages
run OpenWrt VM compatibility matrix
collect test evidence
check release metadata/version parity
release preflight
detect stale merged worktrees
generate a PR evidence summary
```

These should eventually be encoded in repository scripts and GitHub Actions so agents do not have to remember them.

### Keep owner-gated

Do not fully automate:

```text
merging
force-pushing
production signing approval
creating/pushing release tags
publishing a public release
replacing a CA
applying live PassWall2 routing
rebooting the router
destructive worktree/stash cleanup when unique work may exist
```

These actions have a larger blast radius or require human product judgment.

---

## Suggested automation maturity

### Phase 1 — now

Use:

```text
AGENTS.md
MASTER_PLAN.md
PROMPTS.md
existing tests
existing GitHub Actions
```

Agents follow the documented workflow.

### Phase 2 — canonical-state verification helper

Use the implemented local helper:

```text
scripts/start-pr.sh
```

It verifies the effective fetch and push destinations before fetching, then
invokes the roadmap-state guard after synchronizing `main`. The same guard can
be run directly after an account, token, or Codex task-context switch:

```text
scripts/verify-roadmap-state.sh
```

It resolves Git URL rewrites, prints the fetched first-parent `main` history,
and blocks when the remote is not canonical, the roadmap baseline is stale, or
the canonical checkout is not clean. Duplicate Works or prior chat context
never override that repository evidence.

The helper can safely:

```text
verify canonical repo
verify clean main
fetch authoritative remote
create one branch/worktree
print the new worktree path
```

Before using or changing this helper:

1. verify the canonical repository, remotes, current branch, commit, upstream,
   and status
2. verify the existing canonical-remote release-preflight behavior remains
   present when the helper is used for release-related work
3. create new task worktrees only under
   `<workspace-root>/worktrees/`

### Phase 3

Use the implemented change-aware PR checker:

```text
scripts/check-pr.sh
```

It:

```text
detects changed file categories
runs focused tests
runs full validation
runs git diff --check
reports whether real router/browser testing is required
optionally writes versioned, secret-free JSON when PR_EVIDENCE_PATH is set
```

See [PR_EVIDENCE.md](PR_EVIDENCE.md) for the schema, `BLOCKED` semantics,
artifact retention, and how package workflows bind built checksums to the same
candidate. Documentation-only pull requests use the evidence-only workflow and
do not invoke an OpenWrt SDK build.

### Phase 4

Add real OpenWrt integration CI:

```text
oldest supported 25.12.x
latest supported 25.12.x
```

and later a separate 24.10/OPKG lane only if legacy support is intentionally added.

### Phase 5

Move toward:

```text
build candidate once
→ test exact artifact
→ approve
→ promote exact artifact
```

rather than rebuilding after testing.

---

## Can the AI workflow itself spawn/delete all Works automatically?

Do not design the project around that assumption.

The durable automation should live in:

```text
Git
repository scripts
tests
GitHub Actions
release gates
```

Those are reproducible regardless of which AI session is active.

Use ChatGPT Works as operator contexts around that automation.

The safest model is:

```text
AI decides/proposes
repository automation proves
owner approves high-risk actions
```

---

## Mental model

A Work is an AI task context.

A Git worktree is an isolated checked-out branch.

An agent role is a prompt/instruction set.

A master plan is the roadmap.

They relate like this:

```text
MASTER_PLAN.md
    says what remains

PROMPTS.md
    defines roles

WORKFLOW.md
    says when to use each role

AGENTS.md
    defines permanent rules

ChatGPT Work
    executes a role

Git worktree
    contains the isolated code being edited
```
