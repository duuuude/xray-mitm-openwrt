#!/usr/bin/env python3
"""Read-only exact-identity CI decisions and registered-chat routing preflight.

No network, scheduler, review, Git, signing or approval operations are performed.
CI callers supply fresh GitHub REST records. Routing callers supply a private
registry pinned by its original digest; a match never grants dispatch authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

MAX_BYTES = 1024 * 1024
MAX_AGE_SECONDS = 300
SHA = re.compile(r"[0-9a-f]{40}\Z")
ACTIVE = {"queued", "in_progress", "waiting", "requested", "pending"}
CONCLUSIONS = {"success", "failure", "cancelled", "timed_out", "skipped",
               "action_required", "neutral", "stale", "startup_failure"}
ROLES = {"lead", "reviewer", "router_validation"}


def routing_decision(registry: dict, role: str, task_id: str) -> dict:
    """Validate destination against a pinned local registry, not permission."""
    invalid = {"state": "HOLD_ROUTING", "protected_authority": "NONE",
               "dispatch_authority": "NONE"}
    try:
        if (set(registry) != {"schema_version", "roles"}
                or type(registry["schema_version"]) is not int
                or registry["schema_version"] != 1
                or set(registry["roles"]) != ROLES or role not in ROLES):
            return invalid
        ids = list(registry["roles"].values())
        if (len(set(ids)) != len(ROLES)
                or any(not isinstance(i, str) or str(UUID(i)) != i for i in ids)
                or task_id != registry["roles"][role]):
            return invalid
        return {"state": "ROUTE_MATCH", "role": role, "task_id": task_id,
                "protected_authority": "NONE", "dispatch_authority": "NONE"}
    except (KeyError, TypeError, ValueError, AttributeError):
        return invalid


def decision(snapshot: dict, repository: str, pr_number: int, head: str,
             base: str, run_ids: tuple[int, ...], now: datetime) -> dict:
    """Pure classification; malformed evidence never grants a gate."""
    def result(state: str, action: str) -> dict:
        return {"state": state, "monitor_action": action,
                "protected_authority": "NONE", "review_gate": "UNPROVEN"}

    invalid = result("HOLD_INVALID", "PAUSE_AND_REFRESH_EVIDENCE")
    try:
        if (not SHA.fullmatch(head) or not SHA.fullmatch(base)
                or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository)
                or type(pr_number) is not int or pr_number <= 0
                or not run_ids or len(set(run_ids)) != len(run_ids)
                or any(type(x) is not int or x <= 0 for x in run_ids)):
            return invalid
        observed = datetime.fromisoformat(snapshot["observed_at"].replace("Z", "+00:00"))
        if observed.utcoffset() is None or not 0 <= (now - observed).total_seconds() <= MAX_AGE_SECONDS:
            return invalid
        pr = snapshot["pr"]
        if (type(pr["number"]) is not int or pr["number"] != pr_number
                or pr["base"]["repo"]["full_name"] != repository
                or type(pr["merged"]) is not bool
                or pr["state"] not in {"open", "closed"}
                or not SHA.fullmatch(pr["head"]["sha"])
                or not SHA.fullmatch(pr["base"]["sha"])):
            return invalid
        if pr["head"]["sha"] != head:
            return result("STOP_SUPERSEDED", "STOP_AND_RECONCILE_ASSIGNMENT")
        if pr["merged"]:
            # Open PR merge_commit_sha can be a prediction, NOT a completed merge.
            if (pr["state"] != "closed" or not pr.get("merged_at")
                    or not SHA.fullmatch(pr.get("merge_commit_sha", ""))):
                return invalid
            if not isinstance(pr["merged_at"], str):
                return invalid
            merged_at = datetime.fromisoformat(pr["merged_at"].replace("Z", "+00:00"))
            if merged_at.utcoffset() is None or merged_at > observed:
                return invalid
            return result("STOP_MERGED", "STOP_AND_RECORD_MERGED_PR")
        if pr.get("merged_at"):
            return invalid
        if pr["state"] == "closed":
            return result("STOP_CLOSED", "STOP_AND_RECORD_CLOSED_PR")
        if pr["base"]["sha"] != base:
            return result("STOP_SUPERSEDED", "STOP_AND_RECONCILE_ASSIGNMENT")
        runs = snapshot["runs"]
        if (not isinstance(runs, list) or len(runs) != len(run_ids)
                or any(type(r["id"]) is not int for r in runs)
                or {r["id"] for r in runs} != set(run_ids)):
            return invalid
        terminal = []
        for run in runs:
            if (not isinstance(run["pull_requests"], list)
                    or any(not isinstance(p, dict) or type(p.get("number")) is not int
                           or p["number"] <= 0 for p in run["pull_requests"])):
                return invalid
            associations = [p for p in run["pull_requests"] if p["number"] == pr_number]
            if (run["repository"]["full_name"] != repository
                    or run["event"] != "pull_request" or run["head_sha"] != head
                    or len(associations) != 1
                    or associations[0]["head"]["sha"] != head
                    or associations[0]["base"]["sha"] != base):
                return invalid
            status, conclusion = run["status"], run["conclusion"]
            if status == "completed":
                if conclusion not in CONCLUSIONS:
                    return invalid
                terminal.append(conclusion)
            elif status not in ACTIVE or conclusion is not None:
                return invalid
        if any(c != "success" for c in terminal):
            return result("STOP_FAILED", "STOP_AND_INSPECT_EXISTING_FAILURE_EVIDENCE")
        if len(terminal) == len(run_ids):
            return result("STOP_CI_TERMINAL", "STOP_CI_POLLING_AND_CHECK_SEPARATE_REVIEW_GATES")
        return result("WAIT", "WAIT_FOR_EXISTING_RUNS")
    except (KeyError, TypeError, ValueError, AttributeError):
        return invalid


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--snapshot", type=Path)
    inputs.add_argument("--role-registry", type=Path)
    parser.add_argument("--registry-sha256")
    parser.add_argument("--role", choices=sorted(ROLES))
    parser.add_argument("--task-id")
    parser.add_argument("--repository")
    parser.add_argument("--pr", type=int)
    parser.add_argument("--head")
    parser.add_argument("--base")
    parser.add_argument("--run-id", type=int, action="append")
    args = parser.parse_args()
    ci_args = (args.repository, args.pr, args.head, args.base, args.run_id)
    routing_args = (args.registry_sha256, args.role, args.task_id)
    if args.role_registry:
        if not all(routing_args) or any(x is not None for x in ci_args):
            parser.error("routing mode requires digest, role and task ID only")
    elif not all(x is not None for x in ci_args) or any(x is not None for x in routing_args):
        parser.error("CI mode requires repository, PR, head, base and run IDs only")
    try:
        with (args.role_registry or args.snapshot).open("rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError("oversize")
        if args.role_registry and (not re.fullmatch(r"[0-9a-f]{64}", args.registry_sha256)
                                  or hashlib.sha256(raw).hexdigest() != args.registry_sha256):
            raise ValueError("registry changed")
        # Duplicate JSON fields would make identities ambiguous.
        def unique(pairs):
            obj = {}
            for key, value in pairs:
                if key in obj:
                    raise ValueError("duplicate field")
                obj[key] = value
            return obj
        snapshot = json.loads(raw, object_pairs_hook=unique)
        if args.role_registry:
            outcome = routing_decision(snapshot, args.role, args.task_id)
        else:
            outcome = decision(snapshot, args.repository, args.pr, args.head, args.base,
                               tuple(args.run_id), datetime.now(timezone.utc))
    except (OSError, ValueError, RecursionError):
        if args.role_registry:
            outcome = {"state": "HOLD_ROUTING", "protected_authority": "NONE",
                       "dispatch_authority": "NONE"}
        else:
            outcome = {"state": "HOLD_INVALID", "monitor_action": "PAUSE_AND_REFRESH_EVIDENCE",
                       "protected_authority": "NONE", "review_gate": "UNPROVEN"}
    print(json.dumps(outcome, sort_keys=True))
    return 1 if outcome["state"] in {"HOLD_INVALID", "HOLD_ROUTING"} else 0


if __name__ == "__main__":
    sys.exit(main())
