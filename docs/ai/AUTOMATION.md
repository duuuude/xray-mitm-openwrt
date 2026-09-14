# Automation Plan

This document defines which parts of the Xray MITM OpenWrt engineering workflow should become deterministic repository automation.

## Objective

Reduce dependence on human or agent memory.

The rule is:

> If a process rule can be checked mechanically, encode it in a script or CI check.

AI should make engineering judgments. Automation should verify repeatable facts.

---

## Stage 1 — Local repository safety

After verifying the canonical repository, remotes, and current state, add a
safe helper for starting a PR. If the helper participates in release work,
verify that the existing canonical-remote release-preflight behavior remains
present.

Target command:

```text
scripts/start-pr.sh <branch-name> <workspace-root>/worktrees/<task>
```

It should:

1. verify it is running from the canonical repository
2. verify authoritative remote configuration
3. verify `main` has no local changes
4. fetch the authoritative remote
5. require local `main` to match/fast-forward safely
6. reject an already-existing branch/worktree
7. create one feature branch
8. create one worktree
9. print branch, base commit, and path

It must never:

- delete branches
- reset dirty work
- force-push
- clean untracked files

Before implementation, require:

1. verification of the canonical repository, remotes, current branch, commit,
   upstream, and status
2. verification of the existing canonical-remote release-preflight behavior
   where relevant
3. creation of any new task worktree only under
   `<workspace-root>/worktrees/`

---

## Stage 2 — PR verification

Target command:

```text
scripts/check-pr.sh
```

It should detect changed file categories and select relevant validation.

Examples:

```text
LuCI JS / rpcd / ACL changed
→ frontend tests
→ full validation
→ mark real browser test REQUIRED

PassWall2 helper changed
→ PassWall2 fixture tests
→ full validation
→ mark AX4200 routing test REQUIRED

installer changed
→ installer tests
→ full validation

docs only
→ formatting/link/basic validation
```

Output should be machine-readable enough for an agent and human-readable enough for the owner.

Example final report:

```text
Focused tests: PASS
Full validation: PASS
git diff --check: PASS

Manual gates:
LuCI browser test: REQUIRED
AX4200 routing test: REQUIRED
Release test: not required
```

---

## Stage 3 — OpenWrt integration CI

Add a real OpenWrt VM/QEMU compatibility layer.

For the currently supported family:

```text
oldest supported 25.12.x
latest supported 25.12.x
```

Test as much as practical of:

```text
real package installation
dependency resolution
rpcd loading
ubus RPC presence
xray-mitmctl status
setup status
certificate lifecycle in disposable state
service lifecycle
package update/removal
```

The VM does not replace AX4200 network testing. It fills the missing integration layer.

---

## Stage 4 — Evidence generation

Have CI or a local script generate a PR evidence artifact containing:

```text
base commit
head commit
changed files
focused tests
full validation result
OpenWrt VM matrix
manual gates still required
```

This makes review evidence consistent.

---

## Stage 5 — Release preflight

`release-preflight.sh` should remain non-destructive.

It may verify:

```text
main branch
clean tree
authoritative remote sync
version
PKG_RELEASE
changelog
tag absence
full validation
required evidence
```

It must stop before:

```text
tag creation
tag signing
push
release publication
production environment approval
```

---

## Stage 6 — Build once, promote

Long-term release flow:

```text
merge approved source
→ build immutable candidate artifacts
→ sign with appropriate candidate/release process
→ install/test exact artifacts
→ owner approval
→ promote the same artifacts
```

Avoid testing one build and publicly publishing a separately rebuilt package when practical.

---

## What remains human/owner controlled

Keep explicit approval for:

```text
product defaults
recommended routing policy
live router routing changes
certificate replacement
reboot
merge
release signing
public release
destructive cleanup with uncertain unique state
```

The goal is not zero human involvement.

The goal is:

> automate repeatable mechanics; preserve human control over judgment and blast radius.
