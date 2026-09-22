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

Documentation-focused candidates use `.github/workflows/pr-evidence.yml` to
run the checker and upload only the bounded JSON artifact. Its path filters do
not invoke either OpenWrt SDK. Package workflows transfer the exact-checker
record between their validate and build jobs, verify its candidate SHA against
the built package provenance, add package/index checksums, and upload the
enriched record separately from the installable package bundle. Temporary
inter-job evidence is retained for one day; final evidence artifacts are
retained for 30 days.

The 24.10 IPK and 25.12 APK records are separate artifacts attached to their
respective exact-head workflow runs. A successful build proves only those
build/checksum steps; it does not complete router, browser, signing, release,
or merge gates.
