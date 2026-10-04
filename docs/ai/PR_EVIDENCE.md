# Machine-readable PR evidence

`scripts/check-pr.sh` can emit a deterministic JSON record for the exact
base/candidate pair. Set `PR_EVIDENCE_PATH` to an explicit file outside the
checkout; without that setting, the checker keeps its existing terminal-only
behavior and does not leave files behind.

```sh
PR_EVIDENCE_PATH="$RUNNER_TEMP/pr-evidence.json" \
  sh scripts/check-pr.sh "$BASE_SHA" "$CANDIDATE_SHA"
```

The file uses schema version `1` and contains:

- full base and candidate commit SHAs, sorted changed paths, and sorted change
  categories;
- the check names, exact display commands, `PASS`/`FAIL`/`SKIPPED` results,
  exit codes, and safe skip reasons;
- manual gates with `required`, `not_required`, or `owner_gated` status, named
  owner, and `performed: false` until a separate authorized validation records
  evidence;
- additive `package_gates` describing applicable APK/IPK workflows from the
  candidate's actual event path filters, with `performed: false`; these are
  requirements, never proof that GitHub scheduled or completed a build;
- package files with SHA-256 and byte size, when a package workflow enriches
  the record after building and verifying the candidate; and
- the checker result and a small allowlist of non-secret GitHub run metadata.

The record never includes command output, environment dumps, credentials,
private router state, certificates, or signing material. JSON keys and path
and category lists are stable; no wall-clock timestamp is emitted. Check order
is preserved because it records the order in which checks actually ran.

`READY_FOR_REVIEW` means only that this offline checker passed and found no
required manual gate. It is not reviewer approval or merge authorization.
`BLOCKED` preserves outstanding manual gates or blocking skipped checks.
`FAILED` records one or more failed checks. In CI, setting
`CHECK_PR_ALLOW_MANUAL_GATES=1` lets a package build continue after successful
offline checks while retaining `BLOCKED` in the evidence; it never converts a
failed check, unknown path, or missing evidence into success.

Every pull request to `main` uses `.github/workflows/pr-evidence.yml`, whose
stable check name is **PR validation**. It has no path filter or job-level skip,
checks out the exact head, runs the checker, then verifies fresh source evidence
against the expected base/head and clean Git diff. Missing/malformed/stale
evidence, failed universal checks and blocking offline skips fail this check.
`CHECK_PR_ALLOW_MANUAL_GATES=1` can preserve outstanding *manual* gates as
`BLOCKED`; it cannot clear a missing offline check in this universal workflow.
Evidence is generated outside the checkout in a fresh run, not accepted from a
committed PR file. Integrity validation is not authentication of untrusted PR
code; independent review remains mandatory for workflow/helper changes.

The universal workflow uses read-only contents permission, no secrets, no
persisted checkout credentials and no `pull_request_target`. No SDK or protected
operation is part of this check. Draft, synchronized, reopened, ready-for-review
and edited PRs are covered; conflicting PRs and commit-message skip directives
can still prevent GitHub from running a workflow. Do not interpret absence as
success. There is no merge-queue support in this change.

A green **PR validation** check means offline validation only, not overall merge
readiness. The Lead must separately verify applicable exact-head SDK workflows,
independent review and required manual evidence before requesting owner merge
approval. No controller or GitHub protection setting is introduced here.

Roadmap-only changes no longer schedule APK SDK compilation on PR or main push.
Main `CHANGELOG.md` changes still schedule APK builds, as do package/version
inputs. A future release-preparation main commit must have a successful
**push/main build at that exact SHA** before it is tagged. The publisher still
rejects older-head, PR and dispatch artifacts. If main advances for documentation
after a build, do not tag that unbuilt SHA or weaken provenance; prepare a
coherent owner-approved release commit that triggers the main build. This change
does not create, sign or replace an existing release/tag.

The package-gate filter reader deliberately supports only the current quoted
exact paths and directory `/**` patterns. Unsupported scheduling syntax fails
closed and needs an explicit parser/test update; it is not a general YAML or
GitHub glob engine. Unknown changed paths still fail the existing checker.

Package workflows transfer the exact-checker
record between their validate and build jobs, verify its candidate SHA against
the built package provenance, add package/index checksums, and upload the
enriched record separately from the installable package bundle. Temporary
inter-job evidence is retained for one day; final evidence artifacts are
retained for 30 days.

The 24.10 IPK and 25.12 APK records are separate artifacts attached to their
respective exact-head workflow runs. A successful build proves only those
build/checksum steps; it does not complete router, browser, signing, release,
or merge gates.
