# Current-state and monitor lifecycle contract

This is the normative coordination rule for roadmap drift, local resume
checkpoints and PR CI monitors. It does not replace the independent review and
immutable report/ACK protocol, release qualification, or owner approvals.

## Roadmap baseline is an audit point, not a moving target

`scripts/verify-roadmap-state.sh` refreshes verified GitHub main and requires a
clean, synchronized main checkout. Exactly one baseline must identify an
existing ancestor commit. Every intervening commit is inspected, including
merge parents and side branches; a relevant change followed by a revert still
requires reconciliation.

Only additions/modifications of the regular, non-executable
`docs/ai/MASTER_PLAN.md` file (and empty commits) qualify as bookkeeping.
README, instructions, other docs, tests, scripts, workflows, product files,
unknown paths, deletions, renames and mode/symlink changes are not allowlisted.
A series of qualifying commits returns `READY` without rewriting the baseline.
`READY` means planning-state freshness only, not review or release readiness.

`STALE` means inspect and reconcile relevant changes; `BLOCKED` means resolve
identity, ancestry, cleanliness or concurrent-change uncertainty. Update the
roadmap for meaningful milestones, preferably in the related coherent change,
not in a mandatory plan-only PR after every merge. A directly owner-assigned
repair of this coordination mechanism may proceed on an isolated branch from
verified main after documenting the stale history; it may not claim that the
old plan became ready or waive product/release gates.

## One current checkpoint, separate historical events

### Bind the existing three chats before acting

Record the exact established chat IDs for `lead`, `reviewer` and
`router_validation` in one private role registry, with its original SHA-256 in
Current state. The registry has `schema_version: 1` and a `roles` object with
exactly those three keys and three distinct canonical UUID strings. Do not
commit personal chat IDs. Verify each binding against the actual chat before
recording it; a title, template, memory or agent name is not an identity.

Before a specialist assignment, preflight the destination with the existing
read-only helper:

```sh
python3 scripts/coordination-state.py --role-registry /absolute/roles.json \
  --registry-sha256 ORIGINAL_REGISTRY_SHA256 \
  --role router_validation --task-id EXACT_REGISTERED_CHAT_ID
```

`ROUTE_MATCH` proves only local registry consistency, not live identity, status,
message authorization or permission for an operation. Refresh the exact chat's
latest turn under AGENTS.md and inspect a completed previous turn before sending.
Never interrupt/duplicate an active assignment. Malformed, altered, missing,
duplicate or mismatched bindings return `HOLD_ROUTING`/exit 1. Do not replace
the digest merely to make a failed preflight pass.

Lead implements and coordinates; PR Reviewer independently reviews exact source;
Router & Release Validation owns authorized live-router/browser and release
qualification. Lead must not absorb specialist execution because its tools are
available. Messaging and protected operations still require their separate
human authorization. If a registered chat is unavailable or an alternate chat
is proposed, stop and obtain owner agreement before changing the binding; never
silently substitute another agent or create a permanent fourth chat.

Existing valid reports keep their original identities and protocol. A historical
routing mistake alone is not a reason to repeat review, rewrite report IDs or
invalidate evidence. Record the exception and use the registered roles for new
assignments. Monitor the active specialist through completion and the applicable
verified receipt, not just CI. Use one bounded follow-up, pause on completion or
blocker, and keep restoration unproven until its evidence is read. Do not leave
staged router files awaiting owner visual acceptance: restore before stopping.

Keep a secret-free task-scoped checkpoint outside tracked files. Its first
section is **Current state**, with these required fields:

```text
Objective:
Updated at (UTC):
Owner-authorized operations (exact scope; never infer authority):
Repository / worktree / branch:
Expected base / candidate / PR / existing run IDs / review task and report IDs:
Observed identities and evidence timestamps:
Gates: each PROVEN / PENDING / BLOCKED / UNPROVEN, with evidence references:
Active monitor identity and stop condition, or NONE:
Next safe action:
Owner action: exact decision or NONE:
```

Historical events follow in a separate append-only section. They do not
override Current state. Before resuming, read Current state, refresh live
evidence, reconcile any new owner message and update that section. Update after
every material transition and before stopping or switching tasks. Do not copy
old statements such as “no signature exists” into current state after they
cease to be true. A checkpoint is a record, not evidence or an authorization.

Every owner-facing progress/completion update ends with the current result,
next recommendation and owner action (or `NONE`). Never ask the owner to relay
routine reports. Protected merge, signing, publication and router operations
still need their applicable explicit approvals.

## A monitor has one exact assignment and a terminal disposition

Collect fresh GitHub REST PR and existing workflow run records. For a PR CI
monitor, use the read-only `scripts/coordination-state.py` classifier:

```sh
python3 scripts/coordination-state.py --snapshot /absolute/local/snapshot.json \
  --repository duuuude/xray-mitm-openwrt --pr 123 \
  --head FULL_EXPECTED_HEAD --base FULL_EXPECTED_BASE \
  --run-id EXISTING_RUN_ID
```

The snapshot has `observed_at` (timezone-aware ISO timestamp captured at the
start of collection), `pr` (REST pull-request detail record, including `merged`)
and `runs` (list of REST workflow-run detail records). Supply every assigned
run once and no others; multiple `--run-id` arguments are allowed. Collect all
records during that observation, not from cached summaries. Records older than
five minutes, future timestamps, ambiguous identities or malformed evidence
return `HOLD_INVALID` and exit 1. Valid classifications exit 0, including
failure: exit 0 is **not** a success/review/merge gate.

| State | Required coordinator action |
| --- | --- |
| `WAIT` | Keep the existing monitor, quiet while unchanged; keep actual-build-start checkpoint rules. |
| `STOP_CI_TERMINAL` | Stop this CI poller; record results and inspect separate review/ACK gates. |
| `STOP_FAILED` | Stop this assignment; inspect existing failure logs, distinguish proven cause from unknown, report recovery recommendation. Do not rerun automatically. |
| `STOP_MERGED` / `STOP_CLOSED` | Stop the obsolete PR assignment and record its disposition. |
| `STOP_SUPERSEDED` | Stop; reconcile changed head/base before any replacement assignment or review. |
| `HOLD_INVALID` | Pause the monitor, report the evidence conflict and perform a bounded refresh; never keep replaying the old assignment. |

For `STOP_*`, the coordinator must pause/remove the corresponding existing
automation using the app's supported automation tool, record that disposition
in Current state and stop polling. For `HOLD_INVALID`, pause before recovery;
do not create a new monitor to recover forgotten state. Use an informative
objective-based name. Repeated identical snapshots produce identical decisions
and do not mutate files, GitHub, schedules or gates. The classifier itself does
not manage app automations; stopping them remains an explicit coordinator step.

The classifier binds repository, PR, head/base, run IDs and PR-event
associations. A run for the wrong head/PR is invalid, never evidence of success.
A merged PR needs `state=closed`, `merged=true`, `merged_at` and a merge SHA;
an open PR's predicted `merge_commit_sha` is not proof of merge. The merged
classification stops polling only; verify actual merged/main state separately
before relying on release provenance. Successful CI always leaves independent
review `UNPROVEN` and protected authority `NONE`. A combined CI/review monitor
must retire only the terminal CI component and continue pending review/ACK
work; stop the whole monitor once all assigned components are terminal.

This change does not alter workflow scheduling, signing tests, the handoff
envelope or the release artifact contract. Those are separately reviewed work.
