# AI Workflow

This document explains how the project owner should use AI agents without accumulating a large number of permanent Works.

## Recommended number of active Works

Keep only **3 persistent Works**:

```text
1. Project Coordinator
2. PR Reviewer
3. Router & Release Validation
```

Create **one temporary Implementation Work** only while a PR is actively being built.

So the normal maximum is:

```text
3 persistent Works
+ 1 active Implementation Work
= 4 Works
```

After a PR is merged and its evidence is recorded, the Implementation Work can be removed. Do not keep one Implementation Work per historical PR.

The reusable agent roles in `PROMPTS.md` are **prompt templates**, not permanent Works.

For example, “Release Agent”, “Git Audit Agent”, and “Compatibility Agent” are roles you invoke when needed. They do not each need a permanent Work.

---

## What each persistent Work does

### Project Coordinator

Persistent.

Use it to:

```text
read current main
read MASTER_PLAN.md
check recent changes
decide the single next PR
write acceptance criteria
update the plan after a merge
```

It should not implement code.

### PR Reviewer

Persistent or periodically refreshed.

Use it to:

```text
review the current feature branch against main
search for regressions
check safety invariants
check scope creep
identify missing tests
```

It should review before seeing the implementer's reasoning where practical.

### Router & Release Validation

Persistent.

Use it for:

```text
AX4200 validation
LuCI browser testing
real-service testing
release preflight
release evidence
```

Router mutations remain owner-gated.

---

## Temporary Implementation Work

Create one when a PR scope has been approved.

Example:

```text
Implementation — routing state parity
```

Give it the Implementation Agent prompt from `PROMPTS.md`.

When the PR is merged:

```text
confirm merge
record evidence
remove associated Git worktree
remove the temporary Implementation Work
```

Then create a fresh Implementation Work for the next PR.

This keeps context small and prevents unrelated tasks from accumulating.

---

## Normal cycle

```text
Coordinator
    ↓
one PR brief

Owner approves scope
    ↓

Temporary Implementation Work
    ↓
code + tests + stop

Reviewer
    ↓
findings only

Implementation Work
    ↓
approved fixes only

Automated validation / CI
    ↓

Router & Release Validation
    ↓
only if required

Owner approval
    ↓

PR / merge
    ↓

remove implementation worktree
remove temporary Implementation Work
    ↓

Coordinator updates MASTER_PLAN.md
```

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

### Phase 2 — after canonical-state verification

Add a small local helper such as:

```text
scripts/start-pr.sh
```

that can safely:

```text
verify canonical repo
verify clean main
fetch authoritative remote
create one branch/worktree
print the new worktree path
```

Before adding this helper:

1. verify the canonical repository, remotes, current branch, commit, upstream,
   and status
2. complete the release-preflight canonical-remote fix when the helper is used
   for release-related work
3. create new task worktrees only under
   `<workspace-root>/worktrees/`

### Phase 3

Add:

```text
scripts/check-pr.sh
```

that:

```text
detects changed file categories
runs focused tests
runs full validation
runs git diff --check
reports whether real router/browser testing is required
```

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
