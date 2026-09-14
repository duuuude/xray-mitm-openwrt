# Xray MITM OpenWrt — Master Plan

Status: current roadmap; last audited 2026-09-14

This plan is based on the actual canonical repository, not on an earlier plan
or historical checkout.

## Authority and review baseline

The authoritative source is:

- Repository: `https://github.com/duuuude/xray-mitm-openwrt.git`
- Public branch: `main`
- Review/audit baseline: `e78f1d9f62b9bca01eb91f369f44b373844e69e4`, the main
  commit inspected when this plan was refreshed
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

The product currently targets official OpenWrt 25.12.x with APK packages.
The public feed and CI use the 25.12.5 `aarch64_generic` SDK baseline, and
the AX4200 is the tested physical router. OPKG/24.10 support is not an open
task; it is outside the current support contract unless explicitly revisited.

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

### Safety, transaction, and installation behavior

- Quick Setup preserves a valid CA and configuration, refuses an unsafe
  manual candidate, and keeps private-key import Advanced-only.
- PassWall2 integration has inspect/validate/recover/stage/preview/backup/
  apply/bounded-activation/verify/rollback behavior, pending-change refusal,
  concurrency locking, and exact restoration coverage.
- Activation results retain only the latest three completed results while
  preserving pending results. The old retention task is closed.
- The installer detects APK and supported official 25.12 releases, gives
  current post-install guidance, creates protected backups, retains the latest
  three matching backups, preserves unrelated files, and has installer
  regression tests. The old stale-completion-text and 25.12.5-floor tasks are
  closed; support proof is a separate remaining item below.

### Release, configuration, and documentation

- Version parity checks, release-note checks, signed-feed checks, and the
  non-destructive `scripts/release-preflight.sh` exist. The old task to add
  release preflight is complete; a new remote-topology defect in that script
  remains below.
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

### Historical planning text removed as obsolete

The old commit/version references, six-step PR sequence, completed-item
checklist, and historical branch/worktree assumptions no longer describe the
repository. They have been removed rather than carried forward as ceremonial
future work.

## Genuine remaining work

### Product correctness

#### P1 — Make setup-guide routing readiness cover the current contract

`luci-app-xray-mitm/htdocs/luci-static/resources/xray-mitm/state.js:202-214`
marks the setup-guide routing step ready only for `google_mitm`,
`google_meet`, `gemini`, or `iran_direct`. The current contract has additional
service bundles, so a valid configuration containing only Google Play,
Android checks, YouTube, Google accounts, Meta, or Fastly can still be shown
as incomplete.

This is a real user-facing correctness issue, not a reason to weaken any
safety check. The fix should define which service selections make the
routing-assistant step complete, keep the two advanced policy toggles from
being mistaken for service selection by themselves, centralize the predicate,
and add a test for every supported service bundle plus the no-selection case.
Because this changes LuCI behavior, it requires the real browser gate.

#### P2 — Make read-only routing state truthful for partial rules

PassWall2 inspection currently treats a bundle as active after finding a
representative line, for example `domain:googlevideo.com`,
`domain:meet.google.com`, `geosite:meta`, or `geosite:fastly` in the relevant
rule. Apply-time verification is stricter than this inspection predicate.
Consequently, a partially edited or hand-created rule can be reported as
active even when the complete managed bundle is not present.

This needs a focused contract decision: either inspect must verify the full
managed bundle and target/assignment, or the result must be explicitly
described as a sentinel-level signal rather than full activation. Add
regressions for partial lists, wrong targets, aggregate rules, and compatible
legacy rules. Do not expose raw UCI data or credentials while improving the
status.

## Workflow and tooling work

### Present automation

- `scripts/validate-release.sh` runs the offline validator and layered shell,
  Python, and frontend checks.
- CI validates and builds noarch APKs with the pinned official SDK action.
- `scripts/release-preflight.sh` is intentionally non-destructive and checks
  main, cleanliness, remote identity, synchronization, version/changelog/tag
  state, and full validation.
- `scripts/router-local-test.sh` provides controlled manual staging and
  restoration. The physical-router and desktop-browser gates remain manual by
  design.

### Missing or incomplete automation

1. **Release preflight topology.** The canonical checkout has the verified
   GitHub repository in `origin`, but `scripts/release-preflight.sh` defaults
   to a remote named `github`. Its tests model that obsolete name, and
   `docs/RELEASE_TESTING.md` still describes `origin` as a local mirror. The
   default preflight therefore cannot run against the canonical checkout.
   This is the immediate workflow correctness defect.

2. **Safe PR/worktree start helper.** `scripts/start-pr.sh` does not yet
   exist. The intended helper should validate the canonical repository and
   remote, create one branch and worktree under `worktrees/`, and refuse
   ambiguous or dirty source state. It must not delete or reset user work.

3. **Change-aware PR check.** `scripts/check-pr.sh` does not yet exist. It
   should classify changed files, select the relevant offline tests, report
   required manual gates, and fail closed when a category needs evidence that
   is missing. It must not imply that static tests prove router behavior.

4. **Machine-readable evidence.** No standard artifact records base/head,
   changed files, exact commands, test results, built-artifact checksums, and
   browser/router gate ownership. This should follow the change-aware check,
   not replace human approval.

5. **Build-once promotion.** The PR build and tag-triggered signed-feed build
   currently build separately. The long-term workflow should prove that the
   tested package bytes, metadata, and source commit are the exact bytes later
   signed and published. Signing remains protected and owner-controlled.

## OpenWrt compatibility work

The current compatibility claim is narrower than “all OpenWrt”:

- Package metadata is APK/noarch-oriented and uses `@USE_APK` dependencies.
- CI and the public feed use the official 25.12.5 `aarch64_generic` SDK.
- Documentation describes official 25.12.x, but there is no automated oldest-
  versus-latest 25.12.x integration matrix.
- AX4200 is covered by manual router/browser evidence; no automated VM/QEMU or
  disposable-router lane currently proves install, upgrade, removal, ubus/
  rpcd/LuCI behavior, Xray service behavior, certificate status/download,
  PassWall2 inspect/plan/apply/status, recovery, and no-automatic-routing
  behavior across the supported series.

The next compatibility initiative should establish the support matrix and
evidence boundary for the official 25.12 series. It should use disposable
VM/QEMU or equivalent official images for repeatable integration checks, keep
the AX4200 browser gate as a separate physical-device check, and narrow the
published support claim if a release cannot be proven. It should not silently
add OPKG/24.10 support or replace the physical-router gate with mocks.

The build workflow also accepts arbitrary `workflow_dispatch` release and
architecture strings while the publish workflow is fixed to one baseline.
The compatibility initiative must decide whether to enforce a documented
matrix or clearly label manual inputs as unsupported experiments.

## Priority order and PR discipline

Only the first item is active. The rest are queued; do not start a later item
in parallel with an active PR.

| Priority | One coherent PR / initiative | Type | Reason |
| --- | --- | --- | --- |
| 1 | Reconcile release preflight with canonical GitHub `origin` | Workflow correctness | The existing release gate fails on the canonical remote topology. |
| 2 | Make setup-guide routing readiness cover every supported service bundle | Product correctness | A valid current configuration can be shown as incomplete. |
| 3 | Define and enforce truthful partial-bundle inspection | Product correctness | Read-only status can overstate a partially edited rule. |
| 4 | Establish repeatable official OpenWrt 25.12.x compatibility evidence | Compatibility/testing | The support claim is broader than the current automated proof. |
| 5 | Add safe `start-pr.sh` worktree/branch setup | Workflow/tooling | Prevents recurrence of unmanaged sibling workspaces. |
| 6 | Add change-aware checks and a machine-readable evidence report | Workflow/tooling | Makes the correct validation and manual gates auditable. |
| 7 | Build once and promote the exact tested artifact | Release workflow | Removes the remaining PR-build/tag-build provenance gap. |

## Recommended next PR

### `fix: make release preflight use the canonical GitHub remote`

Scope one workflow defect only:

- Make the default path work with the canonical checkout's verified
  `origin`, or safely discover the exact verified GitHub remote.
- Keep exact URL validation and synchronization checks.
- Update `tests/test_release_preflight.py` to model the real remote name and
  to reject a wrong URL before fetch.
- Update `docs/RELEASE_TESTING.md` so it no longer describes `origin` as a
  local mirror.
- Preserve the non-destructive behavior: no tag, push, reset, clean, force,
  signing-key, router, or product-code changes.

Acceptance criteria:

- In a clean product checkout with only the verified GitHub `origin`, the
  default preflight reaches and passes its existing version, changelog, tag,
  synchronization, and full-validation checks.
- A missing or non-authoritative remote fails closed before fetch or release
  checks; an explicit remote override, if retained, is also URL-validated.
- Tests cover success, wrong URL, missing remote, divergence, local/remote tag
  collisions, dirty state, and the no-push/no-tag contract using a local test
  fixture or equivalent network-safe remapping.
- `sh scripts/validate-release.sh`, bundled Node syntax/frontend tests, and
  `git diff --check` pass on the candidate branch.
- The PR changes only the preflight script, its tests, the directly affected
  release-testing documentation, and necessary test fixtures. It does not
  modify product behavior or signing material.

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
- No OPKG/24.10 compatibility without a separately approved support decision.
- No broad Xray rule expansion or unrelated product redesign.
- No permanent sibling clones; temporary task worktrees belong under
  `worktrees/`.
- No merge, tag, release, force-push, or signing action merely because tests
  are green.

The next state change should be the single preflight-topology PR above. After
that PR is reviewed and accepted, revalidate this plan against the resulting
main commit before selecting the next queued item.
