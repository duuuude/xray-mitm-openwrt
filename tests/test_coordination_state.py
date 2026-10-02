#!/usr/bin/env python3
"""Secret-free API fixtures for exact-assignment monitor lifecycle decisions."""
import copy
import importlib.util
import json
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/coordination-state.py"
spec = importlib.util.spec_from_file_location("coordination_state", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class CoordinationStateTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 2, tzinfo=timezone.utc)
        self.head, self.base = "a" * 40, "b" * 40
        self.repo = "duuuude/xray-mitm-openwrt"
        association = {"number": 91, "head": {"sha": self.head}, "base": {"sha": self.base}}
        self.snapshot = {
            "observed_at": self.now.isoformat(),
            "pr": {**copy.deepcopy(association), "state": "open", "merged": False,
                   "merged_at": None, "merge_commit_sha": "c" * 40},
            "runs": [{"id": n, "repository": {"full_name": self.repo},
                      "event": "pull_request", "head_sha": self.head,
                      "pull_requests": [copy.deepcopy(association)],
                      "status": "in_progress", "conclusion": None} for n in (1, 2)]}
        self.snapshot["pr"]["base"]["repo"] = {"full_name": self.repo}

    def classify(self):
        out = module.decision(self.snapshot, self.repo, 91, self.head, self.base, (1, 2), self.now)
        self.assertEqual(out["protected_authority"], "NONE")
        self.assertEqual(out["review_gate"], "UNPROVEN")
        return out["state"]

    def test_open_predicted_merge_is_not_completed(self):
        self.assertEqual(self.classify(), "WAIT")

    def test_merged_stops_even_when_base_has_advanced(self):
        self.snapshot["pr"].update(state="closed", merged=True, merged_at=self.now.isoformat())
        self.snapshot["pr"]["base"]["sha"] = "d" * 40
        self.assertEqual(self.classify(), "STOP_MERGED")

    def test_closed_without_merge(self):
        self.snapshot["pr"]["state"] = "closed"
        self.assertEqual(self.classify(), "STOP_CLOSED")

    def test_head_or_base_change_supersedes(self):
        for field in ("head", "base"):
            with self.subTest(field=field):
                self.snapshot["pr"][field]["sha"] = "d" * 40
                self.assertEqual(self.classify(), "STOP_SUPERSEDED")
                self.snapshot["pr"][field]["sha"] = self.head if field == "head" else self.base

    def test_all_success_stops_ci_not_review(self):
        for run in self.snapshot["runs"]:
            run.update(status="completed", conclusion="success")
        self.assertEqual(self.classify(), "STOP_CI_TERMINAL")

    def test_failure_and_other_non_successes_stop(self):
        for conclusion in module.CONCLUSIONS - {"success"}:
            self.snapshot["runs"][0].update(status="completed", conclusion=conclusion)
            self.assertEqual(self.classify(), "STOP_FAILED")

    def test_partial_success_waits(self):
        self.snapshot["runs"][0].update(status="completed", conclusion="success")
        self.assertEqual(self.classify(), "WAIT")

    def test_wrong_run_identity_is_not_ready(self):
        for field, value in (("id", 3), ("head_sha", "d" * 40), ("event", "push")):
            with self.subTest(field=field):
                old = self.snapshot["runs"][0][field]
                self.snapshot["runs"][0][field] = value
                self.assertEqual(self.classify(), "HOLD_INVALID")
                self.snapshot["runs"][0][field] = old

    def test_wrong_repository_or_association(self):
        for target in (self.snapshot["pr"]["base"]["repo"], self.snapshot["runs"][0]["repository"]):
            target["full_name"] = "other/repo"
            self.assertEqual(self.classify(), "HOLD_INVALID")
            target["full_name"] = self.repo
        self.snapshot["runs"][0]["pull_requests"][0]["base"]["sha"] = "d" * 40
        self.assertEqual(self.classify(), "HOLD_INVALID")

    def test_missing_duplicate_runs_and_malformed_records(self):
        original = copy.deepcopy(self.snapshot)
        for runs in ([], [original["runs"][0]] * 2, [None, {}]):
            self.snapshot["runs"] = runs
            self.assertEqual(self.classify(), "HOLD_INVALID")

    def test_stale_future_or_naive_snapshot_pauses(self):
        for when in (self.now - timedelta(seconds=301), self.now + timedelta(seconds=1), self.now.replace(tzinfo=None)):
            self.snapshot["observed_at"] = when.isoformat()
            self.assertEqual(self.classify(), "HOLD_INVALID")

    def test_inconsistent_status_and_merge_fail_closed(self):
        self.snapshot["pr"]["merged"] = True
        self.assertEqual(self.classify(), "HOLD_INVALID")
        self.snapshot["pr"]["merged"] = False
        for status, conclusion in (("completed", None), ("unknown", None), ("queued", "success")):
            self.snapshot["runs"][0].update(status=status, conclusion=conclusion)
            self.assertEqual(self.classify(), "HOLD_INVALID")

    def test_repeated_wakes_are_idempotent_and_do_not_mutate(self):
        before = copy.deepcopy(self.snapshot)
        self.assertEqual(self.classify(), self.classify())
        self.assertEqual(before, self.snapshot)
        for run in self.snapshot["runs"]:
            run.update(status="completed", conclusion="success")
        self.assertEqual(self.classify(), self.classify())

    def test_cli_rejects_duplicate_fields_and_oversize_without_echo(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "snapshot.json"
            for raw in ('{"secret":"do-not-echo", "secret":"again"}', "x" * (module.MAX_BYTES + 1)):
                path.write_text(raw)
                result = subprocess.run(["python3", str(SCRIPT), "--snapshot", str(path),
                    "--repository", self.repo, "--pr", "91", "--head", self.head,
                    "--base", self.base, "--run-id", "1", "--run-id", "2"], capture_output=True, text=True)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(json.loads(result.stdout)["state"], "HOLD_INVALID")
                self.assertNotIn("do-not-echo", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
