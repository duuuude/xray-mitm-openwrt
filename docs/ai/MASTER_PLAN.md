# Xray MITM OpenWrt — Master Plan

Status: current roadmap; last audited 2026-09-30

This plan is based on the actual canonical repository, not on an earlier plan
or historical checkout.

## Authority and review baseline

The authoritative source is:

- Repository: `https://github.com/duuuude/xray-mitm-openwrt.git`
- Public branch: `main`
- Review/audit baseline: `8e8c6c550f0436fc4cfb51a0ce2659b7646e2ad9`, current
  `main` at this audit after PR #82.
- Observed package baseline: `0.4.5-r1` in development metadata; the latest
  published release remains `v0.4.4` for the 25.12/APK feed (as of 2026-09-30)
- Canonical clone root: `<repo-root>`
- Temporary task worktrees: `<workspace-root>/worktrees/`

This public plan intentionally contains no personal filesystem path, live
checkout-status claim, local branch/worktree inventory, or local-only commit
identifier. Every agent must verify the live repository path, branch, commit,
remotes, upstream, and status before acting.

Use one canonical clone for repository work and create isolated task worktrees
only under `<workspace-root>/worktrees/`. Any destructive cleanup must follow
the safety rules in `AGENTS.md`; ambiguous work is not removed automatically.

Recent merged evidence:

- PR #62 exact candidate `047d08a1bb78b1d3492efacaf6d8f3535e22441e` was
  protected-signed as artifact `10697846012`, installed on the AX4200, tested
  with the guarded helper, rolled back through the trusted feed, and restored
  byte-for-byte. Post-merge 24.10/IPK and 25.12/APK verification both passed.
  The full helper install/remove lifecycle from a PassWall2-disabled,
  fallback-absent state and native 24.10/IPK runtime remain unproven.

- PR #61's build-once promotion path was merged in `main` as
  `12bf2d5a66f6ad381dbf21988ebf90e9e4bf4572`. The main build records exact
  source and package checksums; the protected tag workflow resolves, verifies,
  and reuses that artifact without rebuilding packages. A real protected tag
  publication remains an owner-gated release execution, not an unverified
  support claim.

- PR #63 merged this roadmap reconciliation as
  `4cddc4c7a8f03fd288c1d94cd4f43caa31aa6694`; it changed documentation only.

- PR #65 merged as `2c1b73015f5ff52e108c744123323a3079f5fa9c` from exact
  candidate `2f309c1bdd43f574f263d85e5cebde08e0f8ea06`. It added versioned,
  secret-free PR evidence and bound package checksums to that evidence. Exact
  candidate CI and both post-merge package builds passed. This proves the
  workflow/artifact path, not protected release publication or native
  24.10/IPK runtime behavior.

- PR #66 merged as `5da74654fa18c8ab2ab4f42d1ce086a1676e81da`; it reconciled
  this roadmap after PR #65. It changed documentation only.

- PR #67 merged as `395f1dde5caa6f82cccc7505b012ef9ffd7a7e07`. It added
  fail-closed task-status checks and verified direct delivery of complete
  reviewer reports, including response-shape tests. It changed project
  workflow and documentation, not product behavior.

- PR #68 merged as `24a7af1bf3ba109c470979c4ecd17af5ab73a951`; it reconciled
  this roadmap after PR #67 and recorded PR #66/#67 evidence. Documentation
  only.

- PR #69 exact candidate `be38d183de37ec4be025912c6be5b7647f01da58` merged
  as `6bc5b37387b0c5b02c9121f1a8d931d9717b7671`. Exact-head PR Evidence
  run [35924725216](https://github.com/duuuude/xray-mitm-openwrt/actions/runs/35924725216),
  APK run [35924725080](https://github.com/duuuude/xray-mitm-openwrt/actions/runs/35924725080),
  and 24.10 IPK run
  [35924725091](https://github.com/duuuude/xray-mitm-openwrt/actions/runs/35924725091)
  succeeded. The owner-authorized bounded AX4200 staging/check/restore test
  passed and verified restoration of the protected baseline by hashes; it
  installed no package and made no persistent router-configuration change.
  Both post-merge main package builds passed. This is bounded staging-helper
  evidence on the tested router, not native 24.10/IPK runtime support or a
  broader product-release claim.

- PR #70 merged as `0b64460182d6273094cb4446552918845a1eab41`; it reconciled
  the roadmap after PR #69 and retained the separate owner-gated protected
  release and native 24.10/IPK runtime gates.

- PR #71 merged as `935f173916b8a864614bf188193cfb3f673ab308`. It hardened
  task-status and reviewer-report handoff rules, including preventing
  self-targeted probes and treating safety/policy rejection as terminal. This
  is agent-process guidance and test coverage, not product-runtime evidence.

- PR #72 merged as `76398e234d3d6381c876682e2de142fa6c4e9aaa`. It added the
  repository-scoped Codex `network_access = true` setting for GitHub CLI and
  other authorized workspace commands. It does not add credentials or change
  application/package behavior. Its `.codex/config.toml` path is excluded by
  the existing package and PR Evidence workflow filters; no exact-commit
  workflow run was present in the 2026-09-25 audit.

- PR #73 merged as `1455399b7e0bd9dff19bbb98e03811b3b128c4d2`. It added
  bounded, immutable local Work-report handoffs and exact report/receipt
  verification. Its exact-candidate PR Evidence, APK, and 24.10 IPK checks
  passed. It improves agent coordination but does not change Codex task-history
  rendering or provide cross-device report synchronization.

- PR #74 merged as `1747a5d6ef8d1fe8db2868b33feadcbfa13679b7`. It established
  code-first operations and a bounded same-task continuation only after a
  verified usage-limit failure and elapsed reset. This is guidance-only and
  grants no additional merge, signing, release, or router authority.

- PR #75 merged as `0b3dbbef5dd3e3a7c7c093866aa2495ef7d0dcb9`. The complete
  `scripts/validate-release.sh` passed locally on this exact `main` commit,
  including the previously failing PassWall2 restart-recovery test. The
  post-merge APK workflow run
  [36193558094](https://github.com/duuuude/xray-mitm-openwrt/actions/runs/36193558094)
  also succeeded for this exact commit. No IPK workflow ran for this
  documentation-only change; these results do not prove a protected release,
  signed artifact, native 24.10/IPK runtime, or router behavior. The earlier
  full-validator failure's root cause remains unknown; the current exact-main
  full run satisfies the green-validator prerequisite without explaining that
  earlier failure.

- PR #76 merged as `e15966435975f5509ab19d6c93d84a00af039bd2`; it reconciled
  this roadmap after the validator pass recorded for PR #75. Documentation
  only; it added no package, router, or release evidence.

- PR #77's exact reviewed candidate `ecd32edf3e3808cc91debb3eb3b5784d0ec8d941`
  was squash-merged as `a3bf576c5a52682e6844fe0f9d14767665dfa112`. It prepares
  v0.4.5 metadata and user-facing version labels. Exact-candidate PR Evidence
  run [36269627949](https://github.com/duuuude/xray-mitm-openwrt/actions/runs/36269627949),
  APK run [36269627890](https://github.com/duuuude/xray-mitm-openwrt/actions/runs/36269627890),
  and 24.10 IPK run
  [36269627892](https://github.com/duuuude/xray-mitm-openwrt/actions/runs/36269627892)
  all succeeded. The candidate's source tree is identical to the merged main
  tree. Post-merge APK run
  [36273118365](https://github.com/duuuude/xray-mitm-openwrt/actions/runs/36273118365)
  and 24.10 IPK run
  [36273118289](https://github.com/duuuude/xray-mitm-openwrt/actions/runs/36273118289)
  also succeeded for exact main `a3bf576c5a52682e6844fe0f9d14767665dfa112`.
  The main APK artifact digest is
  `sha256:727cacc6b2876d233f12aad6915d90cf5390d04836c99f5dc490d826daf28117`;
  its local promotion-artifact verification passed. No `v0.4.5` tag or
  published release exists as of this audit; these results are build and
  source-validation evidence, not protected signing, installation, or release
  evidence.

- PR #78 merged as `5b2924ebd0b36a812fbf79c3b93f4f07ba6b902d`; it reconciled
  the v0.4.5 roadmap after PR #77. Documentation only. It did not create a
  signing workflow or perform signing, installation, or publication.

- PR #79 merged as `9f13a53823988b221bbe6f607d93966c15304a54`. It added the
  local-only, fail-closed v0.4.5 lab signer, pinned to a previously successful
  main APK artifact and limited to signing `packages.adb`; it does not rebuild
  or publish packages. Exact-candidate PR Evidence, APK, and 24.10 IPK runs
  `36324776417`, `36324776457`, and `36324776476` succeeded. The merge added
  tooling only; it did not itself perform signing or installation.

- PR #80 merged as `e3cf035b671682051ec1a71f35598d3dd3275519`. It corrected
  the local signer to invoke the APK tool at its actual path in the pinned
  SDK image. Exact-head APK run `36615662307` succeeded. It did not itself
  perform signing, installation, or publication.

- PR #81 merged as `f7fb4d5f4396562d096490e2190b8e8f90ec4352`. It runs the
  signer checksum check from the correct directory and scopes the
  untrusted-input option to the local signing flow while retaining strict
  post-sign verification. Exact-head APK run `36626686675` succeeded. Its
  changes did not sign or publish a package.

- PR #82 merged as `8e8c6c550f0436fc4cfb51a0ce2659b7646e2ad9`. It replaced
  the stale version-labeled dashboard image with a genuine current capture
  framed to omit version-specific UI, and updated both README languages to
  reference the same version-neutral image. Exact-candidate PR Evidence
  succeeded; package builds were not applicable to the docs/media-only diff
  under the existing path filters.

- After PR #81, the owner-authorized private lab flow signed only
  `packages.adb` for the previously built v0.4.5 package artifact. Strict
  signature verification passed and both APKs remained byte-identical. With
  separate owner authorization, only the two v0.4.5 packages were installed
  offline on the AX4200; configuration, service, certificate, and routing
  checks passed, and the LuCI page rendered v0.4.5 in Chrome with no captured
  error-level console entries. This is private lab evidence tied to the older
  source artifact, not a public release or current-main build. A router health
  check was not run, a generated `.apk-new` file and the rollback snapshot
  were intentionally left untouched, and cleanup of the temporary public
  package feed remains pending. No tag, release, or public feed publication
  occurred.

The merged PRs and private lab checks above do not complete a protected
release or establish native 24.10/IPK runtime support.

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
- The installer detects matching official release/backend pairs: 25.12.x with
  APK and 24.10.x with OPKG. The existing APK trust, targeted upgrade, backup,
  and rollback behavior is preserved. The OPKG path requires explicit HTTPS
  feed/key inputs and a SHA-256 pin, requires OPKG signature checking to be
  enabled, preserves unrelated feed entries, performs targeted install/upgrade
  operations, and restores feed state on failure. It intentionally has no
  default public 24.10 feed or production signing path; missing OPKG trust or
  feed inputs fail closed. Installer regression coverage covers both backends.
  The old stale-completion-text and 25.12.5-floor tasks are closed; native
  24.10 runtime and publication proof remain separate items below.

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
product-correctness PR is active. PR #59's compatibility Stage 4
capability/fallback implementation and PR #62's guarded router DNS fallback
correction are complete. PR #62 passed bounded 25.12/APK live package,
service, DNS, and WAN checks, trusted rollback, byte-for-byte recovery, and
post-merge verification. Its full disabled-PassWall2/fallback-absent lifecycle
remains unproven, and native 24.10/IPK runtime behavior remains unproven. PR
#65 completed the machine-readable evidence initiative below; do not treat
that tooling completion as additional product or compatibility evidence.

### Validation reliability

The configured-Node full `scripts/validate-release.sh` passed on the exact
PR #81 candidate `742e8adec95da64b5018c0919dcdd3c8bfaedb48`; its exact-head
APK workflow also succeeded. Current `main` is
`8e8c6c550f0436fc4cfb51a0ce2659b7646e2ad9`, after the docs/media-only PR #82.
The latest successful `push` APK run is `36631809160` for parent commit
`f7fb4d5f4396562d096490e2190b8e8f90ec4352`; there is no APK workflow run
for the exact current `main` SHA. Do not treat that parent artifact as an
exact-current-main artifact or as eligible for the pinned signer/publisher.
An earlier full run on `76398e234d0b36a812fbf79c3b93f4f07ba6b902d` failed
`test_second_hung_restart_is_not_retried_by_exit_recovery` after observing one
restart attempt instead of two; its targeted rerun passed (1/1). The earlier
failure's cause remains unproven and must not be described as diagnosed.

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
in-scope corrections. Stage 6 promotion was completed for this candidate. The
protected exact-candidate signing and live validation gate was completed for PR
#62 before merge. PR #61 then implemented the build-once promotion path: the
tag-triggered protected workflow resolves and verifies the successful main-build
artifact for the exact release commit, and signs the reused package index
without rebuilding package bytes. Actual protected tag/publication execution
remains owner-gated.
Stage 7 was not required because the candidate was documentation-only. Stage 8
was then qualified for bounded local operation through the replay and safety
cases recorded below. The default three-Work workflow remains the supported
operating mode; unattended cutover is not qualified. PR #48 then completed
the P1 partial-bundle inspection item with independent source review, protected
artifact validation, AX4200 integration, synthetic-state inspection, trusted
rollback, and exact recovery comparison. The official OpenWrt compatibility
initiative has completed its contract, package-build, dual-backend installer,
and capability-fallback implementation stages. Stage 3 evidence is now recorded
with bounded 25.12/APK service and rollback proof and an explicit 24.10/IPK
native-runtime limitation. PR #59's exact candidate passed both package CI
lanes, protected signing, bounded 25.12/APK AX4200 package/runtime validation,
and trusted rollback; the complete evidence record is
`docs/OPENWRT_24_25_STAGE4_EVIDENCE.md`. Its required LuCI/browser gate remains
unproven because the router certificate did not match the browser hostname and
no bypass was allowed. Native 24.10/IPK runtime behavior also remains
unproven. Later stages remain separately scoped and reviewed, not one platform
build.
PR #62 then corrected the guarded router DNS fallback and passed exact-head
package CI, protected signing, AX4200 25.12 package/runtime validation,
trusted rollback, and post-merge 24.10/IPK plus 25.12/APK verification. Its
remaining helper lifecycle and native 24.10/IPK limits stay explicit.
PR #61's promotion implementation is also complete; only a real protected
tag/publication run remains an owner-gated operational release step.
PR #65 then implemented the standard evidence artifact: `scripts/check-pr.sh`
emits deterministic schema-version-1 JSON alongside its human report, the PR
Evidence workflow uploads exact-candidate evidence, and both package workflows
bind verified package checksums to that same record. The merged PR and its
successful post-merge package builds qualify this tooling path only; they do
not complete a protected release or native 24.10 runtime validation.
PR #68 reconciled this plan after PR #67. PR #69 then hardened the router-local
staging backup trust/restore path; its exact CI and bounded AX4200 evidence are
listed above. Neither change completes the separate protected release gate.
`docs/ai/AUTONOMOUS_PR.md` records the stage order, independence, cost boundary,
and owner gates. No unattended router/release authority is approved by this
scheduling decision.

The truthful partial-bundle inspection defect is complete in PR #48, and the
compatibility capability/fallback implementation slice is complete in PR #59.
Its remaining browser and 24.10 evidence boundaries are recorded in
`docs/OPENWRT_24_25_STAGE4_EVIDENCE.md`. Recheck the roadmap after every
owner-approved merge before selecting another PR.

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
- `scripts/pr-evidence.py` emits deterministic, secret-free schema-version-1
  evidence; PR Evidence uploads it for documentation candidates, and package
  workflows attach checksummed build evidence to the same exact candidate.
- `scripts/router-local-test.sh` provides controlled manual staging and
  restoration. The physical-router and desktop-browser gates remain manual by
  design.

### Remaining owner-gated release evidence

**Protected release execution evidence.** The build-once promotion path is
   implemented and fails closed on source, metadata, package-byte, and checksum
   mismatches. A real owner-approved tag-triggered publication still needs to
   exercise that path and record the resulting release, Pages, and signed-feed
   evidence; no release should be inferred from offline tests alone. This is an
   operational owner gate, not missing implementation work.

## OpenWrt compatibility work

The approved compatibility initiative is documented in
`docs/OPENWRT_COMPATIBILITY.md`. Its initial families are official 24.10.x
using OPKG/IPK and official 25.12.x using APK. The public 25.12 contract stays
in force while 24.10 remains an unproven legacy target.

- 24.10.8 and 25.12.5 are the reference releases and must be revalidated when
  a build or release stage starts.
- The first 24.10 target is `aarch64_cortex-a53`, matching the physical lab
  router; a generic SDK build alone is not hardware evidence.
- Existing 25.12 APK packaging, signed-feed trust, installer behavior, and
  AX4200/browser gates remain protected.
- No local x86 emulation, Docker VM, firmware downgrade, or replacement of the
  physical-router gate is part of the plan.
- PassWall2 remains optional; standalone service capability and integration
  capability must be evidenced separately.

Stage 0 contract work, Stage 1 package-build work, and Stage 2 installer
mechanics are complete. Stage 3 has bounded 25.12/APK standalone-service,
certificate-preservation, configuration-preservation, recovery, and rollback
evidence; 24.10/IPK native runtime and hardware evidence are explicitly
unproven because no compatible target was available. The 25.12 APK path remains
public and protected; 24.10 OPKG requires enabled signature checking plus
explicit authenticated feed inputs and has no default public feed. Production
publication and final 24.10 support claims remain future gates.

The guarded router DNS fallback correction is complete in PR #62. Its protected
candidate passed the 25.12/APK live gate and exact recovery; this does not
establish native 24.10/IPK runtime support.

The build workflow also accepts arbitrary `workflow_dispatch` release and
architecture strings while the publish workflow is fixed to one baseline.
The compatibility initiative must decide whether to enforce a documented
matrix or clearly label manual inputs as unsupported experiments.

## Priority order and PR discipline

No implementation PR is active. The lab signer and local install have been
exercised, but used the successful main APK artifact from
`a3bf576c5a52682e6844fe0f9d14767665dfa112`; the current exact main commit has
no APK artifact. Do not reuse the successful build for
`f7fb4d5f4396562d096490e2190b8e8f90ec4352` as though it were built from
current `main`. Router health-check status and temporary-feed cleanup are also
outstanding. No v0.4.5 tag or public release exists; lab validation is not
release publication.

The full validator is green on exact PR #81 candidate
`742e8adec95da64b5018c0919dcdd3c8bfaedb48`, not on current documentation-
updated `main`. The protected release's next state change remains separately
owner-gated and requires a fresh full-validator pass on its exact final
candidate, alongside current-main artifact and other release evidence.

| Priority | Next action / initiative | Type | Reason |
| --- | --- | --- | --- |
| 1 | Include only `docs/ai/MASTER_PLAN.md` in the APK workflow's existing push-to-main and pull-request path filters | CI/tooling PR | The screenshot-only PR #82 did not trigger a main APK build. A narrow path entry will make roadmap-only main commits produce the exact-SHA APK artifact without broad `docs/**` builds or weakening publisher provenance checks. |
| 2 | Exercise build-once promotion for one exact, owner-approved release commit | Owner-gated release operation | This later gate proves the protected tag workflow reuses verified main-build bytes and records public release/Pages evidence; it must remain separate from lab validation. |

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
the required three-Work operating model. At the time of this qualification,
the official OpenWrt compatibility evidence initiative was the next active
implementation item; its capability/fallback implementation slice is now
complete in PR #59 and its guarded router DNS fallback correction is complete
in PR #62, with the remaining gates recorded in
`docs/OPENWRT_24_25_STAGE4_EVIDENCE.md`.

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

## Completed release workflow record — PR #61

### Release workflow — build once and promote the exact tested artifact

The compatibility implementation and guarded DNS fallback correction are
complete in PRs #59 and #62, with the bounded evidence and remaining
browser/24.10 limitations recorded in
`docs/OPENWRT_24_25_STAGE4_EVIDENCE.md`. PR #61 closes the provenance gap
between the artifact tested during main-build validation and the artifact later
signed or published; a real protected tag/publication run remains a separate
owner-gated release operation.

Scope:

- Bind the built package bytes and metadata to the exact reviewed candidate
  commit and record their checksums.
- Reuse or cryptographically verify those exact bytes in the protected signing
  and publication path instead of rebuilding an independent copy.
- Fail closed when source, package metadata, artifact bytes, or release inputs
  do not match.

Out of scope:

- Public 24.10 support or release publication.
- Native 24.10/IPK runtime claims; those remain a separate physical-router
  evidence gate.
- Automatic routing, certificate replacement, broad firewall/DNS changes, or
  unattended signing/release authority.

Acceptance criteria:

- The exact reviewed candidate, built artifact checksums, package metadata, and
  later signed/published bytes are demonstrably identical.
- Independent review, protected signing, release ownership, and router gates
  remain separate and fail closed on missing or mismatched evidence.
- Existing 25.12/APK behavior, the dual-backend installer boundaries, and the
  compatibility fallback remain unchanged.

## Completed v0.4.5 private lab-sign path

### Local-only lab-sign path for the exact v0.4.5 main artifact

The owner-approved helper reused the successful APK artifact for source
`a3bf576c5a52682e6844fe0f9d14767665dfa112`; it did not rebuild packages.
Signing completed for `packages.adb` only, strict verification passed, and
both APK files remained byte-identical. The resulting bundle stayed in a
private local temporary session and was not uploaded. With separate owner
authorization, the two packages were installed offline on the AX4200; the
configuration, service, certificate, routing, and Chrome page checks recorded
above passed. This completed only a private lab validation, not a public
release or a current-main build.

Acceptance criteria:

- The local helper fails closed on source-run, SHA, artifact, and checksum
  mismatches.
- Sign only `packages.adb`; do not rebuild or rewrite either APK.
- The output stays in the private local temporary session; the cleanup target is manual,
  and do not upload the bundle.
- Preserve release separation: no public tag, Release, Pages deployment, or
  feed publication is part of this completed lab task.

The exact current `main` artifact gap, router health check, and temporary-feed
cleanup are separate remaining work below.

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

## Recommended next state change

### Produce an exact-current-main APK artifact

The successful main APK run currently available is for
`f7fb4d5f4396562d096490e2190b8e8f90ec4352`, the parent of current `main`
`8e8c6c550f0436fc4cfb51a0ce2659b7646e2ad9`. The screenshot-only PR #82 did
not trigger the package workflow, so its artifact is not exact-current-main
evidence.

The next source PR should add only `docs/ai/MASTER_PLAN.md` to the `push` and
`pull_request` path filters in `.github/workflows/build.yml`. Do not broaden
the trigger to all documentation or weaken the publisher's successful
`push`/`main`/exact-SHA checks. After that workflow PR is reviewed and merged,
reconcile this plan again; the later plan-only merge will trigger an APK
`push` run for its exact merge SHA. Verify run event, branch, SHA, artifact
identity, and checksums before using that artifact in any consumer. The
existing local lab signer remains pinned to its historical source commit, run,
and artifact ID; it rejects artifacts outside that provenance. A newly
generated current-main artifact cannot be consumed by the current local signer
unless a separate, reviewed change updates those pins. Keep this local signer
path distinct from the protected publisher's exact-SHA flow and provenance
checks.

Run the authorized read-only router health check when the Chrome/router
connection is available. The known temporary public package feed remains
pending cleanup. Router authentication grants access, not authorization: do
not remove the feed unless the owner separately approves the exact cleanup
after the target and proposed command are inspected and a rollback/state-
preservation plan is recorded. The earlier SSH cleanup attempt was denied.
Until separately approved, preserve the rollback snapshot and generated
`.apk-new` configuration file.

The full validator is green on the reviewed PR #81 candidate only; it has not
been rerun on current `main`. The next planned state change for protected
tag/publication evidence is the exact-current-main APK artifact and a fresh
full validator/preflight. Public release remains owner-gated, and native
24.10/IPK runtime behavior remains unproven. Do not begin optional automatic
routing or claim public 24.10 support from package builds alone. Do not repeat
the completed evidence-artifact initiative, build-once implementation, or
compatibility Stage 4 capability/fallback work.
Revalidate this plan after the qualification and after every later
owner-approved stage merge. Do not repeat the completed autonomous-PR Stage 4
work or select a later compatibility stage without current-main verification.
