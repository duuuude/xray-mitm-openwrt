# Durable review handoff: normative v2 pilot specification

Status: **additive pilot, not adopted as an approval gate**. Generic v1
`write`, `verify`, `read`, `read-final`, `ack`, and `verify-ack` retain their
existing contract. A real pilot must pass both v1 and v2. Independent protocol
review and a separate explicit owner decision are required before replacing
the v1 completion/ACK gate. Implementing or merging this pilot is not adoption.

## Authority and storage

One structured review is authoritative for the v2 pilot. Presentation is
generated from it, not a second independently authored verdict. An immutable
Lead-observed terminal record and one receipt complete delivery. Verifying
that receipt is deterministic: no new Reviewer reasoning turn is needed for
v2. The real pilot still performs today's source and Lead v1 ACK checks.

Use `scripts/work-report-handoff.py` with an explicit **stable canonical
repository root** for `--repo`, not a disposable implementation worktree.
Commit objects for the exact base/head must remain available there. All v2
records live under `.codex/handoffs/<exact Lead task UUID>/review-v2-*.json`.
This ignored private directory is independent of the review checkout's lifetime.
Old v1 records remain at their original locations and are not moved, deleted,
converted or invalidated. The generic v1 format stays available for non-Git
reports; do not invent PR/base/diff fields for router-only or other reports.

All records are bounded, mode0600, no-overwrite JSON with canonical SHA-256;
directories and lock files are private. The same pinned-root, no-symlink,
regular-file and atomic-link safeguards apply. A nonblocking private lock
serializes one store's writes/reads; a busy store fails promptly, not forever.
No mutable index, background worker, network notification, CI scheduling,
merge, owner authorization, signing, or router operation is performed.

Hashes establish consistency, **not authorship or judgment**. A process with
local write access can forge records and hashes; task UUIDs do not authenticate
that process. The completion observer must independently verify the source
task/turn and reconcile context. The pilot never grants protected authority.

## Frozen assignment, exact reviewed diff

Lead creates one immutable `assign-review` record before sending the review:

```sh
python3 scripts/work-report-handoff.py assign-review \
  --repo '<stable canonical repository root>' \
  --source-task-id '<independent Reviewer UUID>' \
  --destination-task-id '<Lead UUID>' \
  --assignment-id '<unique assignment ID>' \
  --repository duuuude/xray-mitm-openwrt --pr '<positive exact PR number>' \
  --base-sha '<full assigned base>' --candidate-sha '<full assigned head>' \
  --diff-sha256 '<expected complete Git diff SHA-256>'
```

The diff digest is SHA-256 of the exact bytes returned by:

```sh
git diff --binary --full-index --no-ext-diff --no-textconv --no-renames \
  '<full assigned base>' '<full assigned head>' --
```

Base/head must be existing commits, base must be an ancestor, the bounded full
diff must match, and all effective `origin` fetch/push URLs must name this
canonical GitHub project. No working-tree summary substitutes for commit bytes.
PR identity comes from the independently refreshed GitHub assignment; the
local helper cannot prove the live PR still points to those commits. Lead must
refresh live PR/base/head before relying on review and before an owner gate.

Lead saves the returned **assignment SHA-256** in Current state and supplies
that exact digest to the Reviewer. Every subsequent command requires it:

```text
--repo <same stable canonical root>
--source-task-id <same exact Reviewer UUID>
--destination-task-id <same exact Lead UUID>
--assignment-id <same unique assignment ID>
--assignment-sha256 <exact digest from the original assignment>
--report-id <unique report ID>
```

These arguments below are called `COMMON`. This is notation, not a shell
command. Never derive the expected assignment digest from an incoming report.
The digest binds repo/PR/base/head/full diff/tasks/assignment before a receipt
is accepted. Account changes or unavailable notification history do not alter
it. Missing original assignment evidence is HOLD, not permission to reconstruct
a new assignment from the candidate's claims.

## Structured report and generated final

The source creates a private bounded JSON input containing exactly:

```json
{
  "verdict": "APPROVE",
  "findings": [],
  "unresolved_conflicts": [],
  "supersedes": null,
  "analysis": "Complete review evidence, scope, proven/unproven boundaries and rationale."
}
```

Allowed verdicts: `APPROVE`, `CHANGES REQUESTED`, `BLOCK`. Each finding has
exactly `id`, `severity` (`blocker|high|medium|low`), `status` (`OPEN|RESOLVED`)
and nonempty `summary`; IDs are unique. Analysis supplies locations, impact,
minimal fixes and test/evidence details. Conflicts are explicit nonempty strings.
APPROVE cannot coexist with open findings or conflicts. Any unresolved context
conflict requires BLOCK. This structural check does not interpret prose or
prove a review is correct; Lead still evaluates evidence and contradictions.

Source runs `write-review COMMON --source-turn-id <exact active review turn>
--report-file <private JSON file>`, then `verify-review COMMON`. The report is
immutable and binds the assignment digest and source review turn. Verification
prints full structured evidence and leaves completion `UNPROVEN`. Delete only
the source's disposable input after successful read-back; preserve the records.

For the real dual-path pilot, the source also writes a v1 report with the same
report ID/tasks/head, whose complete body equals v2 `analysis` exactly. Its
generated final is the output of `render-review COMMON --include-analysis
--legacy-v1`: the unchanged v1 body followed by one `XRAY_HANDOFF_V2=` JSON
receipt, including the verified v1 receipt. No separate human-authored final
verdict/caveat is appended. The source must not write terminal completion for
its own still-running turn or claim receipt before the observer verifies it.

V2-only synthetic fixtures may omit `--legacy-v1` and the optional analysis
prefix. Markdown code fences, JSON indentation, Markdown hard breaks in the
identical analysis prefix and trailing well-formed memory-citation metadata
are presentation only. They do not require re-review or rewriting the report.
Arbitrary surrounding notes, a changed receipt, duplicate marker, invalid JSON,
or extra correction text fail closed. Citation metadata is not review evidence.

## Terminal completion and one deterministic receipt

Lead first observes the exact source task/turn completed, then reads/reconciles
its final. `complete-review COMMON --source-turn-id <exact assigned report turn>
--sessions-root <local sessions root> --confirm-final-reconciled --legacy-v1`
requires exactly one matching local terminal event and generated receipt.
Missing/ambiguous/interrupted/future completion remains pending; a source-written
report or notification alone never completes review. Extra final corrections
block completion rather than being accepted by a containment test.

Only after that succeeds, Lead runs `receipt-review COMMON` and immediately
`verify-review-receipt COMMON`. The receipt binds the assignment, report,
terminal-completion digest and receiving Lead UUID, and is explicitly receipt-
only, `pilot_only=true`, `protected_authority=NONE`. Receipt of BLOCK or CHANGES
REQUESTED is allowed but cannot become APPROVE. Verification can be repeated
locally without another model turn, native delivery or rescanning historical
session layouts. Persisted completion is a Lead attestation, not a live status
query; lost logs after verified completion do not require a replacement report.
Before initial completion, missing logs still HOLD; v1 remains stricter during
the pilot and must also pass its existing reconciliation/ACK gates.

## Corrections and bounded recovery

- Only one initial report ID is reserved per assignment. A duplicate ID cannot
  overwrite it; a competing verdict requires explicit retraction. Interrupted
  initial writing leaves a reservation and no completed gate. After inspecting
  the error, a normal interruption may be recovered by filling that same
  reserved ID only; never automatically retry after a policy/safety rejection.
- For a correction, first run `retract-review COMMON --replacement-report-id
  <new unique ID> --reason <explicit correction>`. This immutable tombstone
  invalidates old report/completion/receipts immediately, even if replacement
  writing or notification then fails. It must not be deferred until a new
  report is ready. New report `supersedes` names the old ID; the exact retraction
  binds old digest and the sole permitted replacement ID. A new terminal turn
  and completion are required. Up to64 reports in one checked lineage are
  supported; excessive or cyclic lineage is HOLD, not endless recovery.
- A changed PR/base/head/diff requires a **new assignment**, not a changed hash
  in the old assignment. Lead marks the old assignment superseded in Current
  state and does not reuse its receipt. The helper cannot silently authorize
  work on another PR or select the receiving task.
- An additional material caveat in a later source message is not automatically
  discovered by this local helper. The coordinator must record it as a
  retraction immediately, hold the gate, and reconcile the latest source
  request/turn before relying on any receipt. Never claim that hashes detect
  semantic contradictions or messages the tool has not read.
- Reports/completions/receipts cannot be overwritten or regenerated just to
  change formatting. Verify/read existing records after a lost tool response.
  Missing completion/receipt is PENDING; malformed identity/hash/path/permission
  evidence is BLOCKED, not green. Tampering requires diagnosis, not repair of
  the hashes. Duplicate terminal events or logs remain HOLD.
- No notification is required for verification. At most one best-effort native
  receipt notification may follow successful artifact verification, only when
  that message is authorized. Failed/rejected notification does not erase an
  already verified artifact. No alternative transport, account switch or
  artifact creation may work around a rejected send. Never ask the owner to
  relay reports. Store busy/path-changed or write failure is reported promptly;
  no replacement monitor or silent spin loop is created.

## Pilot adoption evidence

Run focused v2 failures, all unchanged v1 tests, contract tests and the full
configured-Node validator. Review the complete exact candidate independently
under v1; pilot the same low-risk review through v2 as supplemental evidence.
Record both results and exact identities in Current state. This specification
and its helper do not waive v1, independently approve implementation, or grant
merge, signing, tag, release, cleanup, router/browser or automatic scheduling
authority. Owner adoption approval remains a separate decision after the pilot.
