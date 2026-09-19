# Xray MITM OpenWrt — Master Plan

Status: current roadmap; last audited 2026-09-19

This plan is based on the actual canonical repository, not on an earlier plan
or historical checkout.

## Authority and review baseline

The authoritative source is:

- Repository: `https://github.com/duuuude/xray-mitm-openwrt.git`
- Public branch: `main`
- Review/audit baseline: `24de3d1501103a3bb8089e2fe728e883256ca1ea`, the current
  `main` commit inspected before the OpenWrt compatibility Stage 0 work
- Observed package baseline: `0.4.4-r1`
- Canonical clone root: `<repo-root>`
- Temporary task worktrees: `<workspace-root>/worktrees/`

This public plan intentionally contains no personal filesystem path, live
checkout-status claim, local branch/worktree inventory, or local-only commit
identifier. Every agent must verify the live repository path, branch, commit,
remotes, upstream, and status before acting.

Use one canonical clone for repository work and create isolated task worktrees
only under `<workspace-root>/worktrees/`. Any destructive cleanup must follow
the safety rules in `AGENTS.md`; ambiguous work is not removed automatically.

The current public product contract targets official OpenWrt 25.12.x with APK
packages. The public feed and CI use the 25.12.5 `aarch64_generic` SDK baseline,
and the AX4200 is the tested physical router. The owner has approved a staged
compatibility initiative for official 24.10.x OPKG/IPK and 25.12.x APK families.
24.10 is a legacy-compatibility target with limited security support, not yet a
public support claim; no upstream security maintenance is promised after its
end of life. The exact contract and evidence boundary are in
`docs/OPENWRT_COMPATIBILITY.md`.

The 2026-09-14 audit of baseline
`e78f1d9f62b9bca01eb91f369f44b373844e69e4` recorded passing offline
validation: the release validator, PassWall2, certificate, configuration,
control, installer, signed-feed, and startup suites passed. That audit also
recorded successful bundled-Node JavaScript syntax checks and
`tests/test_frontend_state.js`. These are dated audit evidence, not validation
performed by this documentation correction.

## Governing principles

- Current code, tests, package metadata, workflows, and user documentation are
  authoritative. Historical plans are evidence, not requirements.
- Do not simplify safety mechanisms. Simplify what the user has to understand.
- Preserve the package split: `xray-mitm` and `luci-app-xray-mitm`.
- Preserve the boundary `LuCI → rpcd/ucode → xray-mitmctl → internal helpers`.
  LuCI must not call privileged helpers directly.
- Preserve certificate, private-key, localhost-only, PassWall2 transaction,
  pending-change, lock, recovery, rollback, and no-automatic-routing
  invariants.
- Use one clean branch and one clean worktree from current `main` per change.
  One PR must contain one coherent change. Do not combine product behavior,
  developer tooling, release mechanics, and optional documentation.
- Build and test the exact artifact that will be promoted. Do not touch
  production signing material, rewrite history, force-push, or create tags as
  part of ordinary PR work.
- A LuCI-affecting change requires the real desktop-browser gate on the lab
  router and explicit visual approval. CI, mocks, and static checks do not
  replace that gate.
- Keep router and browser actions owner-controlled. Automation may prepare
  evidence, but it must not silently change routing, certificates, service
  state, or signing configuration.

## Completed work removed from the future roadmap

The following items were future work in the previous master plan.
They are complete in current `main` and must not remain as pending tasks.

### Product behavior and UI

- The backend/frontend routing contract is unified across all twelve routing
  fields. Recommended defaults, including `google_meet: true`, are defined in
  `state.js`, mirrored by the rpc layer, and covered by frontend/control tests.
- Basic routing status is metadata-driven and distinguishes Recommended,
  Custom, and Not configured. The old Basic-status state mismatch is closed.
- Recommended-routing semantics and drift between frontend, backend, and
  persisted state are closed. The Basic UI keeps advanced choices intact and
  exposes the selective routing model and Meet media limitation.
- Google Play, Android checks, YouTube, Google accounts, Google MITM, Google
  Meet, Meta, Fastly, Gemini, and Iran-direct selections are represented by
  the current selective bundles. The old “backend semantics” and “Meet
  default” tasks are obsolete.
- The tabbed Basic/Advanced LuCI structure, state loading, async activation
  lock, activation-result reporting, and current routing summary/table are
  implemented and tested.
- Setup-guide routing readiness now uses one centralized service-selection
  predicate. All ten supported service bundles satisfy readiness, while
  `set_default_vpn` and `set_localhost_proxy_zero` alone do not. Focused
  frontend-state coverage and the exact candidate's AX4200/browser gate closed
  this correctness item. The 2026-09-15 manual check used candidate commit
  `ab9107bccaf963c766965cfa748d6635749ddb35` and temporarily staged only its
  packaged `state.js` on the AX4200. The Overview, Basic Routing, and Advanced
  Routing pages rendered; all ten service selections, no-selection, and both
  policy-only states were exercised; the browser console reported no errors or
  warnings; no save/apply action occurred; and the original file plus recorded
  service, certificate, PassWall2, routing, and unrelated-file state were
  restored and verified. Owner visual approval was recorded. This proves the
  staged LuCI/browser gate, not native APK installation or trusted APK
  rollback.

### Safety, transaction, and installation behavior

- Quick Setup preserves a valid CA and configuration, refuses an unsafe
  manual candidate, and keeps private-key import Advanced-only.
- PassWall2 integration has inspect/validate/recover/stage/preview/backup/
  apply/bounded-activation/verify/rollback behavior, pending-change refusal,
  concurrency locking, and exact restoration coverage.
- Read-only PassWall2 bundle inspection now requires complete managed bundle
  contents, expected networks, valid shunt/rule groups, target assignments, and
  required IP entries. PR #48 added deterministic regressions for partial
  contents, wrong targets, empty or invalid groups, compatible legacy rules,
  and invalid legacy groups. The exact protected candidate was installed and
  rolled back through signed repositories on the AX4200; an isolated real-
  router fixture exercised the synthetic states, and protected package and
  configuration state was restored. This is live integration evidence for the
  inspection behavior, not evidence of external-service behavior.
- Activation results retain only the latest three completed results while
  preserving pending results. The old retention task is closed.
- The installer detects APK and supported official 25.12 releases, gives
  current post-install guidance, creates protected backups, retains the latest
  three matching backups, preserves unrelated files, and has installer
  regression tests. The old stale-completion-text and 25.12.5-floor tasks are
  closed; support proof is a separate remaining item below.

### Release, configuration, and documentation

- Version parity checks, release-note checks, signed-feed checks, and the
  non-destructive `scripts/release-preflight.sh` exist. Preflight now defaults
  to the canonical `origin` remote while still validating the exact GitHub URL
  before fetch; its local-fixture tests cover missing, incorrect, and explicit
  override remotes without network access.
- The packaged Xray configuration audit is documented in
  `docs/CONFIG_AUDIT.md`, with tests for removed and retained behavior. The
  old broad-rule debate, audit-isolation task, and generic maintainability
  cleanup are not roadmap items.
- README, Persian README, Advanced documentation, release testing, security
  guidance, changelog, and the real-browser/manual-router gate describe the
  current product and safety boundaries.
- No separate error-schema project is justified by current evidence. Existing
  action responses have usable error fields; a versioned schema should be
  proposed only when a concrete consumer needs one.

### Workflow and tooling

- Stage 1 of the autonomous PR initiative is complete in merged PR #37. The
  current `main` includes `scripts/start-pr.sh`, which verifies the canonical
  repository and remote, requires an inspectable clean `main`, refuses unsafe
  ancestry, path, branch, worktree, and inspection-error states, and creates
  one isolated feature worktree without destructive Git operations. Its
  focused regression suite is part of the full repository validator.
- Stage 2 is complete in merged PR #39 and is present on `main` at
  `78da93324b6fa3d0ae8f42c717e1e5f7b85cb680`. The current `main` includes
  `scripts/check-pr.sh`, which binds evidence to exact base and candidate
  commits, classifies changed files, runs applicable focused and full offline
  checks, reports skipped checks and manual gates, suppresses candidate command
  output, and rechecks the working tree and HEAD before returning a ready
  result. Its focused regression suite is part of the full repository
  validator. It does not prove live router, browser, release, signing, or
  external-service behavior.
- Stage 3 was qualified and recorded in merged PR #41 with a bounded local
  Codex CLI pilot. The result is a GO for local, scriptable execution under
  explicit sandbox and owner controls, and a NO-GO for an unattended
  controller, CI login, automatic push/PR/merge, release, signing, or router
  authority. The qualification record below is the durable evidence; it does
  not qualify the standard API or Agents SDK under the Plus plan.

### Historical planning text removed as obsolete

The old commit/version references, six-step PR sequence, completed-item
checklist, and historical branch/worktree assumptions no longer describe the
repository. They have been removed rather than carried forward as ceremonial
future work.

## Genuine remaining work

### Product correctness

The P1 partial-bundle inspection defect is complete in merged PR #48. No
product-correctness PR is active. The next approved item is the compatibility
evidence initiative below.

## Workflow and tooling work

### Approved scheduling focus — staged autonomous PR workflow

The owner has chosen the zero-additional-spend autonomous PR initiative as
the current workflow priority. Stage 0 was completed in PR #35 and is present
on `main` at `c69239bb3b1dac04d2edbd2d73d126f2478b778c`. It reconciled the
durable process documentation, PR/CI sequence, independent review boundary,
owner gates, and zero-additional-spend constraint. Stage 1 was then completed
in PR #37, Stage 2 in PR #39, and Stage 3 was qualified in the documented
pilot. Stage 4 was completed through the local vertical slice recorded in PR
#42; the exact candidate received independent approval, both required CI jobs
passed, and the owner-approved squash merge is present on current `main`.
Stage 5 was not invoked because the independent review returned no ordinary
in-scope corrections. Stage 6 promotion was completed for this candidate.
Stage 7 was not required because the candidate was documentation-only. Stage 8
was then qualified for bounded local operation through the replay and safety
cases recorded below. The default three-Work workflow remains the supported
operating mode; unattended cutover is not qualified. PR #48 then completed
the P1 partial-bundle inspection item with independent source review, protected
artifact validation, AX4200 integration, synthetic-state inspection, trusted
rollback, and exact recovery comparison. The official OpenWrt compatibility
initiative is now active at Stage 0. Later stages remain separately scoped and
reviewed, not one platform build.
`docs/ai/AUTONOMOUS_PR.md` records the stage order, independence, cost boundary,
and owner gates. No unattended router/release authority is approved by this
scheduling decision.

The truthful partial-bundle inspection defect is complete in PR #48. Recheck
the roadmap after every owner-approved merge before selecting another PR.

### Present automation

- `scripts/validate-release.sh` runs the offline validator and layered shell,
  Python, and frontend checks.
- CI validates and builds noarch APKs with the pinned official SDK action.
- `scripts/release-preflight.sh` is intentionally non-destructive and checks
  main, cleanliness, remote identity, synchronization, version/changelog/tag
  state, and full validation.
- `scripts/start-pr.sh` verifies repository and remote identity, clean and
  inspectable `main`, safe ancestry, path containment, and collision state
  before creating one isolated feature worktree.
- `scripts/check-pr.sh` binds change-aware validation evidence to exact base
  and candidate commits, runs relevant offline checks, reports manual gates,
  and fails closed on missing evidence or post-validation state changes.
- `scripts/router-local-test.sh` provides controlled manual staging and
  restoration. The physical-router and desktop-browser gates remain manual by
  design.

### Missing or incomplete automation

1. **Machine-readable evidence artifact.** `scripts/check-pr.sh` now emits
   machine-readable and human-readable commit-bound evidence, but no standard
   committed or CI artifact records base/head, changed files, exact commands,
   test results, built-artifact checksums, and browser/router gate ownership.
   This should follow the change-aware check, not replace human approval.

2. **Build-once promotion.** The PR build and tag-triggered signed-feed build
   currently build separately. The long-term workflow should prove that the
   tested package bytes, metadata, and source commit are the exact bytes later
   signed and published. Signing remains protected and owner-controlled.

## OpenWrt compatibility work

The approved compatibility initiative is documented in
`docs/OPENWRT_COMPATIBILITY.md`. Its initial families are official 24.10.x
using OPKG/IPK and official 25.12.x using APK. The public 25.12 contract stays
in force while 24.10 remains an unproven legacy target.

- 24.10.8 and 25.12.5 are the Stage 0 reference releases and must be
  revalidated when build work starts.
- The first 24.10 target is `aarch64_cortex-a53`, matching the physical lab
  router; a generic SDK build alone is not hardware evidence.
- Existing 25.12 APK packaging, signed-feed trust, installer behavior, and
  AX4200/browser gates remain protected.
- No local x86 emulation, Docker VM, firmware downgrade, or replacement of the
  physical-router gate is part of the plan.
- PassWall2 remains optional; standalone service capability and integration
  capability must be evidenced separately.

The current Stage 0 task is documentation/design only. It must finish before
any package, installer, CI, signing, feed, or router implementation begins.

The build workflow also accepts arbitrary `workflow_dispatch` release and
architecture strings while the publish workflow is fixed to one baseline.
The compatibility initiative must decide whether to enforce a documented
matrix or clearly label manual inputs as unsupported experiments.

## Priority order and PR discipline

Only the first item is active. The rest are queued; do not start a later item
in parallel with an active PR. The priority order reflects the owner's
workflow scheduling choice and records completed work separately from the one
active initiative.

| Priority | One coherent PR / initiative | Type | Reason |
| --- | --- | --- | --- |
| 1 | Define and implement the official OpenWrt 24.10/25.12 compatibility initiative, beginning with Stage 0 | Compatibility/design | The owner approved a two-family target, but its evidence and legacy-support boundary must be recorded before implementation. |
| 2 | Build once and promote the exact tested artifact | Release workflow | Removes the remaining PR-build/tag-build provenance gap. |
| 3 | Generate a standard machine-readable PR evidence artifact | Developer tooling | Makes commit-bound tests, checksums, and manual-gate ownership consistent. |

## Completed Stage 3 qualification record — merged PR #41

The qualification was performed on 2026-09-17 against `main` at
`0b1622c44c06731c65239dea5d64bcffe72c084a`.

Official documentation checked:

- [Codex authentication](https://learn.chatgpt.com/docs/auth) states that
  ChatGPT sign-in provides subscription access, API-key sign-in is
  usage-based, and API-key usage is billed at standard API rates. It also
  recommends API-key authentication for programmatic workflows such as CI/CD.
- [Codex pricing](https://learn.chatgpt.com/docs/pricing) states that Codex is
  included with ChatGPT plans, that Plus includes local Codex surfaces, and
  that ChatGPT/Codex usage and limits are shared.
- [Codex CLI](https://learn.chatgpt.com/docs/codex/cli) documents local
  repository work and `codex exec` for repeatable workflows and pipelines.

Pilot identity and invocation:

- Native arm64 Apple M5 Mac with 24 GB RAM; no emulation or Docker runtime.
- Codex CLI `0.154.0-alpha.6.2`.
- `codex login status`: `Logged in using ChatGPT`.
- `OPENAI_API_KEY`, `CODEX_API_KEY`, and `CODEX_ACCESS_TOKEN` were absent from
  the pilot environment.
- The pilot used an ephemeral `codex exec` session with JSON output and the
  CLI `read-only` sandbox against the repository.
- The task was a low-risk repository inspection: verify identity, branch,
  HEAD, clean status, and the active Stage 3 roadmap section. The agent was
  instructed not to edit files, use the network, commit, push, merge, or
  touch router or release state.

Pilot result and measurements:

- The agent returned the expected repository, `main` branch, clean status,
  exact HEAD, active Stage 3, and next-action report.
- Repository state remained clean at the same commit; no repository, router,
  or release files changed.
- Wall time: 93.22 seconds.
- Maximum resident memory: 222,265,344 bytes (about 212 MiB).
- Swap operations: 0; observed system swap usage remained 0 MiB.
- Available root-disk capacity remained about 463 GB before and after the run;
  no disk-pressure concern was observed.
- The CLI reported 137,710 input tokens, 117,248 cached input tokens, 3,836
  output tokens, and 2,680 reasoning tokens for this pilot. Remaining Plus
  capacity and any exact plan accounting were not observable from the CLI.
- The first restricted outer-sandbox attempt could not open Codex local runtime
  state. The successful retry granted only the local runtime permission needed
  by Codex; the repository remained inside the CLI `read-only` sandbox.

Qualification decision:

- **GO:** bounded local, scriptable Codex CLI execution with ChatGPT sign-in,
  an isolated worktree, explicit sandbox permissions, and owner-controlled
  Git actions is qualified for Stage 4.
- **NO-GO:** unattended CI/controller execution, ChatGPT login in GitHub
  Actions, automatic push/PR/merge, release, signing, router, or certificate
  authority is not qualified. The standard OpenAI API or Agents SDK was not
  evaluated or assumed to be included with Plus.

## Completed Stage 4 local vertical slice and PR/CI promotion — merged PR #42

The approved low-risk task used the qualified local Codex CLI in an isolated
worktree from current `main`. The exact candidate was commit
`d438e16871cc69c292f758867f59f1a2adfdab8e` on `docs/stage4-roadmap-sync` and
changed only `docs/ai/MASTER_PLAN.md`.

Evidence and outcome:

- Development Lead validation included exact commit-bound checking, the full
  available repository validator, shell syntax checks, and `git diff --check`.
- The separate read-only Reviewer returned `APPROVE` with no findings.
- PR #42 passed both `validate` and `build` and was squash-merged into `main`
  as `4852f01d75d1e828936f20f9c3778d9f9f0370e8` with the feature branch
  preserved.
- Markdown rendering/link validation was unavailable. LuCI, OpenWrt,
  AX4200/browser, router, release, signing, and external-service behavior were
  not applicable and were not claimed.
- No automatic push, merge, release, signing, router, or certificate
  authority was granted to the local runtime; GitHub publication and the merge
  remained owner-controlled actions.

## Completed Stage 8 qualification and fallback record — bounded local GO

The replay used the qualified native Apple Silicon Codex CLI with ChatGPT
authentication in a read-only sandbox against current `main` at
`1f5a34850236875ac56373c74e67bae873964693`. The isolated worktree branch
`docs/qualify-stage8-fallback` remained exactly aligned with `main` and
`origin/main`; no candidate diff, file edit, commit, push, or network action
was performed by the replay.

Qualification evidence:

- Low-risk replay: the agent read the required governance and workflow
  documents, verified repository identity, canonical remote, branch, HEAD,
  base relationship, clean status, and the sole active stage, then returned the
  expected next-action report without editing the repository.
- Runtime: Codex CLI `0.154.0-alpha.6.2`; `codex login status` reported
  `Logged in using ChatGPT`. No API key or paid runner was used.
- Replay measurement: 235.68 seconds wall time, 221,446,144 bytes maximum
  resident memory (about 211 MiB), zero swap operations, and no repository
  diff. The CLI reported 348,663 input tokens, 292,608 cached input tokens,
  11,762 output tokens, and 8,962 reasoning tokens; exact Plus capacity and
  billing accounting were not observable.
- Injected safety fixtures: `tests/test_check_pr.py` passed 10/10, covering
  secret-output suppression, post-validation dirty/HEAD mutation detection,
  dirty checkout, HEAD mismatch, and unknown paths. `tests/test_start_pr.py`
  passed 20/20, covering Git inspection failures, dirty/diverged main,
  symlink/path containment, and collision refusal.
- Resource and CI evidence: the filesystem reported 463 GiB available at the
  measurement. System-wide swap usage could not be read because the sandbox
  denied `sysctl`; the replay itself recorded zero swap operations. PR #43 CI
  completed successfully: validation took about 3 minutes 46 seconds and the
  build took about 27 minutes 31 seconds.
- No gate violation, secret exposure, router action, release action, signing
  action, or product change occurred. OpenWrt, AX4200/browser, release,
  signing, and external-service behavior were not applicable to this replay.

Qualification boundary:

- **GO:** bounded local, read-only or explicitly scoped local runtime use with
  ChatGPT authentication, isolated worktrees, explicit sandbox permissions,
  fail-closed repository checks, and owner-controlled Git actions.
- **NO-GO:** unattended default-mode cutover, automatic merge/release/signing,
  router/certificate authority, CI login, or any claim that Plus capacity and
  billing are unlimited or fully observable.

This completes the staged autonomous workflow qualification without changing
the required three-Work operating model. The official OpenWrt 25.12.x
compatibility evidence initiative is now the next active implementation item.

## Qualification history

### Stage 8 — qualification and fallback

Use the qualified local runtime for bounded low-risk replays and injected
failure/safety cases. Measure wall time, memory, disk pressure, included-plan
usage boundaries, CI capacity, and any owner-gate or scope violation. Keep
the Development Lead as the routing layer and keep GitHub, release, signing,
router, certificate, and default-mode authority owner-controlled. Do not
assume that a successful replay qualifies unattended operation.

Acceptance criteria:

- Replays use current `main`, one isolated worktree per task, bounded scope,
  explicit sandbox permissions, and no separately billed API or paid runner.
- At least one low-risk project task and the planned injected failure/safety
  cases are replayed with exact before/after repository evidence.
- Measurements record task quality, wall time, memory, disk, usage boundary,
  CI capacity, skipped checks, and any gate violation without exposing secrets.
- Any changed candidate receives focused validation, complete diff inspection,
  and independent review; failed or ambiguous cases stop rather than retry
  indefinitely.
- The result is a qualification or fallback recommendation only. No default
  cutover, unattended merge/release/signing/router authority, or product PR is
  implied by a passing replay.

## Recommended next item

### Stage 0 — define official OpenWrt 24.10/25.12 compatibility contract

The detailed contract is `docs/OPENWRT_COMPATIBILITY.md`. This first PR is
documentation/design only:

- Record official 24.10.x OPKG/IPK and 25.12.x APK as the initial families.
- Record 24.10 as legacy compatibility with limited security support and no
  upstream security promise after end of life.
- Distinguish accepted, built, integration-tested, hardware-tested, and
  published-support evidence.
- Define the first target matrix, separate package/feed trust chains,
  standalone service behavior, and optional PassWall2 capability levels.
- Use native M5 offline tests and bounded GitHub-hosted SDK jobs; do not require
  local emulation, Docker, paid capacity, or an AX4200 firmware downgrade.
- Preserve current 25.12 APK, signed-feed, installer, certificate, PassWall2,
  router, browser, and owner-gate rules.
- Define the ordered Stage 1–6 PR sequence and stop before package or runtime
  implementation.

Out of scope:

- Package, installer, CI, product, or runtime behavior changes.
- Production OPKG signing, feed publication, or release changes.
- Replacing the AX4200 gate with mocks or a local emulator.
- Firmware downgrade, router mutation, or certificate/signing-material action.

Acceptance criteria:

- The two-family matrix, legacy 24.10 boundary, evidence levels, trust design,
  standalone/PassWall2 model, budget, and ordered stages are documented.
- Supported and untested architectures and releases are distinguished.
- No product, installer, package, CI, signing, release, or router behavior is
  changed.
- Documentation validation and the full repository safety validator pass.
- The exact candidate receives independent review and owner merge approval;
  later package, router, browser, signing, and release gates remain separate.

## Validation and release gates for future work

Every candidate starts from current `main`, uses a dedicated worktree under
`worktrees/`, and records its exact base and head. At minimum, run the focused
tests, `sh scripts/validate-release.sh`, bundled Node checks when frontend
files are involved, and `git diff --check`.

For package, installer, service, PassWall2, or LuCI changes, build the exact
APK artifacts and perform the applicable clean-router checks. For LuCI, use a
non-stale real browser session, test the relevant page and state transitions,
inspect the browser console, and obtain explicit visual approval. For release
work, verify the authoritative remote, signed source tag, merged commit,
required CI, artifact checksums, and protected signing-feed approval in the
owner-controlled release sequence.

## Non-goals

- No automatic routing on package installation.
- No certificate regeneration or private-key movement as a convenience.
- No exposure of private keys, credentials, router backups, or secret-bearing
  test data.
- No public 24.10 support claim or release before the later evidence stages and
  owner approval are complete.
- No broad Xray rule expansion or unrelated product redesign.
- No permanent sibling clones; temporary task worktrees belong under
  `worktrees/`.
- No merge, tag, release, force-push, or signing action merely because tests
  are green.

The next state change is the Stage 0 documentation/design PR above. Do not
begin package builds, installer work, build-promotion, or evidence-artifact
work in parallel with it.
Revalidate this plan after the qualification and after every later
owner-approved stage merge. Do not repeat completed Stage 4 work or select a
later stage without current-main verification.
