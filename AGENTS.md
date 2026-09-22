# AGENTS.md

# Xray MITM OpenWrt — Agent Operating Rules

This file defines permanent rules for AI coding agents working on this repository.

Read this file before inspecting, editing, testing, staging, or proposing changes.

## 1. Project

This repository implements a standalone Xray MITM Domain Fronting service for OpenWrt, with a LuCI management interface, certificate lifecycle management, optional PassWall2 routing integration, signed package distribution, conservative install/update behavior, and rollback/recovery paths for risky state changes.

Primary engineering principle:

> **Do not simplify safety mechanisms. Simplify what the user has to understand.**

## 2. Read current code first

Do not assume old plans describe the current implementation.

Always inspect current `main`. Confirm the exact package version, supported OpenWrt versions, routing defaults, Basic/Advanced labels, and service groups from current code/docs.

## 3. Authority and source of truth

Before editing:

1. confirm repository path
2. confirm branch
3. confirm commit
4. confirm configured remotes
5. confirm upstream/tracking branch
6. run `git status --short`

Do not assume a remote named `origin` is necessarily GitHub.

If Git topology is ambiguous, stop and report it before changing code.

## 4. Git rules

- Never implement feature work directly on `main`.
- One branch = one coherent change.
- One PR = one reviewable behavior or tightly coupled fix.
- Do not treat a master plan as one implementation task.
- Do not begin the next planned PR in the same branch.
- Do not refactor unrelated code during a focused fix.
- Do not force-push unless explicitly approved.
- Do not rewrite published release tags.
- Do not merge a PR without explicit owner approval.
- Do not create/publish a release without explicit owner approval.

If another issue is discovered:

```text
report it
→ explain impact
→ suggest a follow-up
→ do not implement it unless it blocks the assigned task
```

## 5. Worktree rules

A worktree is a disposable workspace for one branch.

Preferred model:

```text
canonical main checkout
+
one worktree per active task
```

Before removing a worktree, confirm merge state, dirty files, untracked files, and that no unique work will be lost.

Never remove a dirty or ambiguous worktree automatically.

## 6. Scope protocol

Before making changes, state:

```text
Problem:
Files likely affected:
Behavior expected to change:
Behavior explicitly out of scope:
Tests required:
Router impact:
```

Do not silently broaden scope.

At completion, stop after the assigned scope is done.

## 7. Architecture boundary

Preserve:

```text
LuCI
  ↓
rpcd / ucode
  ↓
xray-mitmctl
  ↓
internal helpers
```

LuCI must not directly execute privileged helpers under `/usr/libexec/xray-mitm/` without an explicitly reviewed architectural reason.

Keep `xray-mitmctl` as the public privileged command boundary.

## 8. Package architecture

Keep the existing package separation unless a clear package-level problem justifies changing it:

```text
xray-mitm
luci-app-xray-mitm
```

Do not introduce micro-packages merely to reduce file size.

## 9. Security rules

Never expose, print, copy into chat, commit, log, or include in screenshots:

- CA private keys
- package-signing private keys
- passwords
- VPN credentials
- subscription URLs
- API keys
- access/session tokens
- router backups
- secret environment values
- private certificate material

Allowed when necessary:

- public certificates
- public keys
- public fingerprints
- synthetic fixtures
- safe status metadata

Do not inspect secret-bearing files unless the assigned task genuinely requires it.

## 10. Certificate safety invariants

Quick/automatic setup must not:

- replace a valid existing CA
- overwrite custom configuration
- silently activate an existing manual candidate
- expose private key material

Private-key import belongs in Advanced behavior only.

Public certificate export must never include private-key material.

## 11. PassWall2 safety invariants

Preserve:

```text
inspect
→ validate
→ recover if required
→ stage privately
→ preview exact change
→ bind apply to exact token
→ backup
→ apply
→ bounded activation/restart
→ verify
→ rollback/recovery
```

Also preserve:

- unrelated user-created PassWall2 rules
- pending-change detection
- exact rollback constraints
- recovery markers
- prevention of concurrent unsafe apply
- refusal to apply MITM-dependent routing when MITM is unavailable
- localhost-only MITM listener assumptions

Do not make routing apply automatically from installation.

## 12. Router safety

Do not automatically:

- alter PassWall2 routing
- replace certificates
- generate a new CA over an existing valid CA
- install PassWall2
- add third-party feeds outside explicit task scope
- change global firewall/DNS
- reboot
- erase state
- restore an old backup over unknown newer state

Router changes must be:

```text
small
explicit
reversible
verified before/after
```

When giving the owner commands, label command blocks:

```text
MAC
ROUTER
```

## 13. Product defaults

Defaults are product policy.

Do not assume the maintainer's personal routing policy should automatically become the universal recommended default.

Changes to fallback/default VPN behavior, recommended service groups, MITM bundles, regional routing, or boot behavior must be called out explicitly as product decisions.

## 14. OpenWrt support

Do not equate installer acceptance with proven support.

Keep separate:

```text
accepted by installer
built successfully
integration-tested
hardware-tested
```

A release family is “supported” only when the project has a repeatable validation path for it.

## 15. Frontend rules

Keep LuCI simple.

Do not introduce React, Vue, Tailwind, SPA frameworks, frontend state libraries, or framework-like folder hierarchies.

Prefer small pure state helpers and minimal render helpers.

A smaller file is not automatically better architecture.

## 16. State-management rule

Derive product state once, then render it in multiple places.

Avoid recomputing setup readiness, routing configured/custom/recommended state, certificate readiness, PassWall2 readiness, or health state independently in several renderers.

Prefer pure shared helpers in `state.js`.

`state.js` should not perform RPC, network I/O, DOM operations, or router mutations.

## 17. Error handling

Errors are part of the API.

Prefer preserving structured errors through:

```text
helper
→ xray-mitmctl
→ rpcd
→ LuCI
```

Avoid degrading a structured error into an opaque JSON string.

## 18. Testing philosophy

Different tests prove different things:

```text
pure/unit test
        ↓
component/contract test
        ↓
real OpenWrt integration
        ↓
real AX4200 system test
        ↓
real external-service behavior
```

Do not claim one layer proves another.

## 19. Required validation

For code changes, run relevant focused tests plus:

```sh
sh scripts/validate-release.sh
git diff --check
git status --short
```

If a required validator is skipped, do not treat the release gate as fully green.

LuCI-affecting changes also require the real-browser gate:

- stage/install exact candidate
- directly reload affected page
- confirm full page renders
- exercise affected controls
- inspect browser console
- confirm no unintended CA/service/routing state change
- obtain explicit owner visual approval

CI alone is not sufficient for LuCI changes.

## 20. Router test evidence

When router testing applies, record:

```text
commit tested
package/candidate version
files or packages staged
pages tested
controls exercised
browser-console result
service state before/after
certificate state before/after
PassWall2 state before/after
rollback/recovery result when relevant
```

Do not report only “router test passed.”

## 21. Release discipline

Normal implementation agents must never:

- create signed tags
- publish GitHub Releases
- approve protected signing environments
- rotate production keys
- modify production secrets

Normal release flow:

```text
features/fixes merged
→ tiny release preparation
→ preflight
→ owner approval
→ signed tag
→ protected publish workflow
```

Do not turn a release branch into a feature branch.

## 22. Build/promotion principle

Long-term target:

> **Build once. Test that exact artifact. Promote that exact artifact.**

Do not assume source-level testing proves a later rebuilt package behaves identically.

## 23. AI-specific behavior

Do not optimize for amount of code generated.

Optimize for:

```text
smallest safe change
clear evidence
reviewability
rollbackability
```

When uncertain, stop and ask rather than inventing architecture.

## 24. Completion report

At the end of an implementation task, provide:

```text
Scope completed
Files changed
Behavior changed
Tests run + exact results
Router changes, if any
Known limitations
Follow-up issues discovered
git status
```

Do not automatically proceed to the next task.

## 25. Golden workflow

After switching ChatGPT accounts, local project tokens, or Codex task contexts,
previous task memory and duplicate Works are not repository state. Refresh the
verified remote through the canonical workflow and run
`sh scripts/verify-roadmap-state.sh` before choosing the next roadmap item.
The guard verifies Git's effective fetch and push URLs after URL rewrites, then
fetches current `main` before comparing the recorded roadmap baseline.
Treat `ROADMAP_STATE=STALE` or `BLOCKED` as a stop condition: inspect the
reported first-parent history, reconcile `MASTER_PLAN.md`, and only then start
new work.

```text
read current main
→ run sh scripts/verify-roadmap-state.sh
→ inspect its recent first-parent main history before selecting roadmap work
→ understand one problem
→ define scope
→ create branch/worktree
→ implement smallest change
→ test
→ inspect diff
→ normal feature-branch push if qualified
→ open one PR and run CI
→ independent review of the exact candidate
→ router/browser test if required
→ owner approval to merge
→ merge only after approval
→ remove worktree only when clean and unambiguous
```

Independent review may occur before or after PR creation, but both review and
CI must apply to the current candidate before the owner merge decision. A
changed candidate requires fresh applicable validation and independent review.
Creating a normal PR or running CI is not itself an owner merge approval.

Apply the same transactional discipline to development that the project already applies to routing.
