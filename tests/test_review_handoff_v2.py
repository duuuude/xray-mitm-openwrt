#!/usr/bin/env python3
"""Executable pilot regressions; never use real reports, keys, or sessions."""
from __future__ import annotations

import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/work-report-handoff.py"
SOURCE = "11111111-1111-4111-8111-111111111111"
LEAD = "22222222-2222-4222-8222-222222222222"
TURN = "33333333-3333-4333-8333-333333333333"
NEXT_TURN = "44444444-4444-4444-8444-444444444444"
spec = importlib.util.spec_from_file_location("handoff_v2", SCRIPT)
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


class ReviewV2Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Synthetic")
        self.git("config", "user.email", "synthetic@example.invalid")
        self.git("remote", "add", "origin", "https://github.com/duuuude/xray-mitm-openwrt.git")
        (self.repo / "file.txt").write_text("base\n")
        self.git("add", ".")
        self.git("commit", "-m", "synthetic base")
        self.base = self.git("rev-parse", "HEAD").strip()
        (self.repo / "file.txt").write_text("candidate\n")
        self.git("commit", "-am", "synthetic candidate")
        self.head = self.git("rev-parse", "HEAD").strip()
        self.diff = hashlib.sha256(self.git("diff", "--binary", "--full-index", "--no-ext-diff", "--no-textconv", "--no-renames", self.base, self.head, "--").encode()).hexdigest()
        self.store = self.repo / ".codex" / "handoffs" / LEAD
        self.report = self.root / "review.json"
        self.review = {"verdict": "APPROVE", "findings": [], "unresolved_conflicts": [],
                       "supersedes": None, "analysis": "Review result: APPROVE\nNo findings.\n"}
        self.input_review(self.review)
        self.assignment_sha = None
        self.sessions = self.root / "sessions"
        self.date = self.sessions / "2026" / "09" / "01"
        self.date.mkdir(parents=True)
        self.log = self.date / f"rollout-2026-09-01T00-00-00-{SOURCE}.jsonl"

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.repo), *args], stderr=subprocess.DEVNULL).decode()

    def input_review(self, review):
        self.report.write_text(json.dumps(review))
        self.report.chmod(0o600)

    def run_cli(self, command, *extra, report_id="review-one", assignment="assignment-one", source=SOURCE):
        args = ["python3", str(SCRIPT), command, "--repo", str(self.repo),
                "--source-task-id", source, "--destination-task-id", LEAD,
                "--assignment-id", assignment]
        if command != "assign-review":
            args += ["--assignment-sha256", self.assignment_sha or "0" * 64, "--report-id", report_id]
        return subprocess.run([*args, *extra], text=True, capture_output=True, timeout=10)

    def assign(self, *extra):
        result = self.run_cli("assign-review", "--repository", "duuuude/xray-mitm-openwrt",
                              "--pr", "92", "--base-sha", self.base, "--candidate-sha", self.head,
                              "--diff-sha256", self.diff, *extra)
        if result.returncode == 0:
            self.assignment_sha = json.loads(result.stdout)["sha256"]
        return result

    def write(self, report_id="review-one", turn=TURN):
        return self.run_cli("write-review", "--source-turn-id", turn,
                            "--report-file", str(self.report), report_id=report_id)

    def prepared(self):
        self.assertEqual(self.assign().returncode, 0)
        self.assertEqual(self.write().returncode, 0)

    def completed_log(self, text, turn=TURN):
        record = {"timestamp": "2026-09-01T00:01:00Z", "type": "event_msg",
                  "payload": {"type": "task_complete", "turn_id": turn, "last_agent_message": text}}
        self.log.write_text(json.dumps(record) + "\n")

    def complete(self, *extra):
        return self.run_cli("complete-review", "--sessions-root", str(self.sessions),
                            "--source-turn-id", TURN, "--confirm-final-reconciled", *extra)

    def delivered(self):
        self.prepared()
        rendered = self.run_cli("render-review")
        self.assertEqual(rendered.returncode, 0)
        self.completed_log(rendered.stdout)
        result = self.complete()
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.run_cli("receipt-review")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_complete_receipt_is_mechanical_and_survives_missing_sessions(self):
        self.delivered()
        self.log.unlink()
        result = self.run_cli("verify-review-receipt")
        self.assertEqual(result.returncode, 0, result.stderr)
        receipt = json.loads(result.stdout)
        self.assertTrue(receipt["pilot_only"])
        self.assertEqual(receipt["protected_authority"], "NONE")
        self.assertEqual(receipt["review_verdict"], "APPROVE")

    def test_dual_v1_v2_pilot_uses_one_review_and_preserves_old_ack(self):
        self.prepared()
        legacy_file = self.root / "legacy.md"
        legacy_file.write_text(self.review["analysis"])
        legacy_file.chmod(0o600)
        common = ["--repo", str(self.repo), "--source-task-id", SOURCE, "--destination-task-id", LEAD,
                  "--report-id", "review-one", "--candidate-sha", self.head]
        written = subprocess.run(["python3", str(SCRIPT), "write", *common, "--title", "Dual pilot",
                                  "--report-file", str(legacy_file)], capture_output=True, text=True, timeout=10)
        self.assertEqual(written.returncode, 0, written.stderr)
        rendered = self.run_cli("render-review", "--include-analysis", "--legacy-v1")
        self.assertEqual(rendered.returncode, 0, rendered.stderr)
        self.completed_log(rendered.stdout)
        self.assertEqual(self.complete("--legacy-v1").returncode, 0)
        for command in ("ack", "verify-ack"):
            args = ["python3", str(SCRIPT), command, *common, "--source-turn-id", TURN,
                    "--sessions-root", str(self.sessions)]
            if command == "ack":
                args += ["--confirm-final-reconciled"]
            result = subprocess.run(args, text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.run_cli("receipt-review").returncode, 0)
        self.assertEqual(self.run_cli("verify-review-receipt").returncode, 0)

    def test_store_path_swap_cannot_claim_delivery(self):
        self.assertEqual(self.assign().returncode, 0)
        args = helper.parser().parse_args(["write-review", "--repo", str(self.repo), "--source-task-id", SOURCE,
                    "--destination-task-id", LEAD, "--assignment-id", "assignment-one", "--assignment-sha256", self.assignment_sha,
                    "--report-id", "review-one", "--source-turn-id", TURN, "--report-file", str(self.report)])
        original_link = helper.os.link
        moved = self.store.with_name("moved-store")
        def swap(*values, **kwargs):
            original_link(*values, **kwargs)
            if values[1] == helper._v2_name("report", "review-one"):
                self.store.rename(moved)
                self.store.mkdir(mode=0o700)
        with patch.object(helper.os, "link", side_effect=swap):
            with self.assertRaises(helper.HandoffError):
                helper.write_review(args)
        self.assertNotEqual(self.run_cli("verify-review").returncode, 0)

    def test_pr_base_head_tampering_cannot_change_frozen_assignment(self):
        self.prepared()
        path = self.store / helper._v2_name("assignment", "assignment-one")
        original = json.loads(path.read_text())
        for key, value in (("pr", 93), ("base_sha", self.head), ("candidate_sha", self.base),
                           ("repository", "another/project"), ("diff_sha256", "0" * 64)):
            doc = helper._seal({**{k: v for k, v in original.items() if k != "sha256"}, key: value})
            path.write_text(json.dumps(doc))
            self.assertNotEqual(self.run_cli("verify-review").returncode, 0)
        path.write_text(json.dumps(original))

    def test_identity_mismatches_block_before_assignment(self):
        for args in [("--repository", "wrong/repo"), ("--pr", "0"),
                     ("--base-sha", "a" * 40), ("--candidate-sha", "b" * 40),
                     ("--diff-sha256", "0" * 64)]:
            with self.subTest(args=args):
                self.assertNotEqual(self.assign(*args).returncode, 0)
        self.assertFalse(self.store.exists())

    def test_changed_effective_push_url_is_rejected(self):
        self.git("remote", "set-url", "--push", "origin", "https://example.invalid/repo")
        self.assertNotEqual(self.assign().returncode, 0)

    def test_assignment_digest_source_and_id_mismatches(self):
        self.prepared()
        for extra in [("--assignment-sha256", "0" * 64),
                      ("--source-task-id", TURN), ("--assignment-id", "another")]:
            self.assertNotEqual(self.run_cli("verify-review", *extra).returncode, 0)

    def test_approve_cannot_have_open_findings_or_conflicts(self):
        self.assertEqual(self.assign().returncode, 0)
        bad = [{**self.review, "findings": [{"id": "F1", "severity": "high", "status": "OPEN", "summary": "Wrong base"}]},
               {**self.review, "unresolved_conflicts": ["Wrong task"]},
               {**self.review, "verdict": "CHANGES REQUESTED", "unresolved_conflicts": ["Wrong task"]},
               {**self.review, "findings": None}, {**self.review, "verdict": "maybe"},
               {**self.review, "supersedes": "../escape"}, {"verdict": "APPROVE"}]
        for value in bad:
            self.input_review(value)
            self.assertNotEqual(self.write().returncode, 0)

    def test_changes_requested_receipt_never_becomes_approval(self):
        self.review["verdict"] = "CHANGES REQUESTED"
        self.review["findings"] = [{"id": "F1", "severity": "high", "status": "OPEN", "summary": "Need fix"}]
        self.input_review(self.review)
        self.delivered()
        result = json.loads(self.run_cli("verify-review-receipt").stdout)
        self.assertEqual(result["review_verdict"], "CHANGES REQUESTED")
        self.assertEqual(result["protected_authority"], "NONE")

    def test_missing_completion_is_pending_and_never_receipted(self):
        self.prepared()
        self.assertNotEqual(self.complete().returncode, 0)
        self.assertNotEqual(self.run_cli("receipt-review").returncode, 0)
        self.assertEqual(json.loads(self.run_cli("verify-review").stdout)["completion"], "UNPROVEN")

    def test_exact_turn_duplicate_completion_and_extra_notes_rejected(self):
        self.prepared()
        rendered = self.run_cli("render-review").stdout
        for message in ["Correction: wrong base\n" + rendered, rendered + "\nActually BLOCK",
                        rendered + rendered, "unrelated", rendered.replace(TURN, LEAD)]:
            self.completed_log(message)
            result = self.complete()
            self.assertNotEqual(result.returncode, 0, message)
        self.completed_log(rendered)
        self.log.write_text(self.log.read_text() * 2)
        self.assertNotEqual(self.complete().returncode, 0)

    def test_rendering_json_spacing_and_optional_metadata_do_not_reissue_report(self):
        self.prepared()
        rendered = self.run_cli("render-review", "--include-analysis").stdout
        body, receipt = rendered.split(helper.V2_MARKER)
        metadata = "\n<oai-mem-citation>\n<citation_entries>\nMEMORY.md:1-2|note=[fixture]\n</citation_entries>\n<rollout_ids>\n</rollout_ids>\n</oai-mem-citation>"
        self.completed_log("```text\n" + body.replace("\n", "  \n") + helper.V2_MARKER + json.dumps(json.loads(receipt), indent=2) + "\n```" + metadata)
        result = self.complete()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_literal_markers_in_analysis_round_trip_but_extra_receipts_do_not(self):
        self.review["analysis"] = 'Discuss `XRAY_HANDOFF_V2=` and a quoted example.\nXRAY_HANDOFF_V2={}\n'
        self.input_review(self.review)
        self.prepared()
        rendered = self.run_cli("render-review", "--include-analysis").stdout
        for bad in (rendered + rendered, rendered + "\nCorrection: BLOCK"):
            self.completed_log(bad)
            self.assertNotEqual(self.complete().returncode, 0)
        self.completed_log(rendered)
        result = self.complete()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_analysis_budget_round_trips_in_both_modes_or_rejects_before_reservation(self):
        # Reserve 16 KiB of the unchanged one-MiB reader budget for both receipts.
        limit = helper.MAX_REPORT_BYTES - 16 * 1024
        for size, legacy in ((limit - 1, False), (limit, False), (limit + 1, False),
                             (limit - 1, True), (limit, True), (limit + 1, True)):
            with self.subTest(size=size, legacy=legacy):
                self.review["analysis"] = "x" * size
                self.input_review(self.review)
                identity = f"budget-{size}-{legacy}"
                assignment = self.run_cli("assign-review", "--repository", "duuuude/xray-mitm-openwrt",
                    "--pr", "92", "--base-sha", self.base, "--candidate-sha", self.head,
                    "--diff-sha256", self.diff, assignment=identity)
                self.assertEqual(assignment.returncode, 0, assignment.stderr)
                self.assignment_sha = json.loads(assignment.stdout)["sha256"]
                written = self.run_cli("write-review", "--source-turn-id", TURN,
                    "--report-file", str(self.report), assignment=identity, report_id=identity)
                if size > limit:
                    self.assertNotEqual(written.returncode, 0)
                    self.assertFalse((self.store / helper._v2_name("initial", identity)).exists())
                    self.assertFalse((self.store / helper._v2_name("report", identity)).exists())
                    continue
                self.assertEqual(written.returncode, 0, written.stderr)
                legacy_args = []
                if legacy:
                    body = self.root / "budget-legacy.md"
                    body.write_text(self.review["analysis"])
                    body.chmod(0o600)
                    result = subprocess.run(["python3", str(SCRIPT), "write", "--repo", str(self.repo),
                        "--source-task-id", SOURCE, "--destination-task-id", LEAD,
                        "--report-id", identity, "--candidate-sha", self.head,
                        "--title", "Boundary fixture", "--report-file", str(body)],
                        capture_output=True, text=True, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    legacy_args = ["--legacy-v1"]
                rendered = self.run_cli("render-review", "--include-analysis", *legacy_args,
                    assignment=identity, report_id=identity)
                self.assertEqual(rendered.returncode, 0, rendered.stderr)
                self.assertLessEqual(len(rendered.stdout.encode()), helper.MAX_REPORT_BYTES)
                self.completed_log(rendered.stdout)
                result = self.run_cli("complete-review", "--source-turn-id", TURN,
                    "--sessions-root", str(self.sessions), "--confirm-final-reconciled", *legacy_args,
                    assignment=identity, report_id=identity)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_conflicting_exact_turn_terminal_events_never_create_completion(self):
        self.prepared()
        rendered = self.run_cli("render-review").stdout
        for event_type in ("turn_aborted", "task_failed", "turn_failed"):
            for before in (True, False):
                self.completed_log(rendered)
                complete = self.log.read_text()
                conflict = json.dumps({"type": "event_msg", "payload": {
                    "type": event_type, "turn_id": TURN}}) + "\n"
                self.log.write_text(conflict + complete if before else complete + conflict)
                self.assertNotEqual(self.complete().returncode, 0, (event_type, before))
                self.assertFalse((self.store / helper._v2_name("completion", "review-one")).exists())
                self.assertNotEqual(self.run_cli("receipt-review").returncode, 0)
        self.completed_log(rendered)
        self.log.write_text(self.log.read_text() + json.dumps({"type": "event_msg", "payload": {
            "type": "turn_aborted", "turn_id": NEXT_TURN}}) + "\n")
        self.assertEqual(self.complete().returncode, 0)

    def test_retraction_invalidates_old_completion_even_if_replacement_missing(self):
        self.delivered()
        result = self.run_cli("retract-review", "--replacement-report-id", "review-two", "--reason", "Corrected base interpretation")
        self.assertEqual(result.returncode, 0, result.stderr)
        for command in ("verify-review", "verify-review-receipt", "receipt-review", "render-review"):
            self.assertNotEqual(self.run_cli(command).returncode, 0)
        self.assertNotEqual(self.write("another").returncode, 0)
        self.review["supersedes"] = "review-one"
        self.input_review(self.review)
        self.assertNotEqual(self.write("review-two").returncode, 0)
        self.assertEqual(self.write("review-two", turn=NEXT_TURN).returncode, 0)
        self.assertEqual(self.run_cli("verify-review", report_id="review-two").returncode, 0)
        self.assertNotEqual(self.run_cli("receipt-review", report_id="review-two").returncode, 0)
        rendered = self.run_cli("render-review", report_id="review-two").stdout
        self.completed_log(rendered, turn=NEXT_TURN)
        result = self.run_cli("complete-review", "--sessions-root", str(self.sessions),
            "--source-turn-id", NEXT_TURN, "--confirm-final-reconciled", report_id="review-two")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.run_cli("receipt-review", report_id="review-two").returncode, 0)
        path = self.store / helper._v2_name("report", "review-two")
        replacement = json.loads(path.read_text())
        replacement["source_turn_id"] = TURN
        replacement.pop("sha256")
        path.write_text(json.dumps(helper._seal(replacement)))
        self.assertNotEqual(self.run_cli("verify-review", report_id="review-two").returncode, 0)

    def test_competing_initial_reports_and_duplicate_writes_rejected(self):
        self.prepared()
        self.assertNotEqual(self.write().returncode, 0)
        self.assertNotEqual(self.write("another").returncode, 0)
        self.assertNotEqual(self.assign().returncode, 0)

    def test_interrupted_initial_write_reserves_only_original_report(self):
        self.assertEqual(self.assign().returncode, 0)
        args = helper.parser().parse_args(["write-review", "--repo", str(self.repo), "--source-task-id", SOURCE,
                    "--destination-task-id", LEAD, "--assignment-id", "assignment-one", "--assignment-sha256", self.assignment_sha,
                    "--report-id", "review-one", "--source-turn-id", TURN, "--report-file", str(self.report)])
        real_save = helper._v2_save
        def fail_report(*values):
            if values[3] == "report":
                raise helper.HandoffError("Synthetic interruption")
            return real_save(*values)
        with patch.object(helper, "_v2_save", side_effect=fail_report):
            with self.assertRaises(helper.HandoffError):
                helper.write_review(args)
        self.assertNotEqual(self.write("another").returncode, 0)
        self.assertEqual(self.write().returncode, 0)
        self.assertNotEqual(self.run_cli("receipt-review").returncode, 0)

    def test_tampering_completion_receipt_or_report_fails_closed(self):
        self.delivered()
        for kind in ("assignment", "report", "completion", "receipt"):
            path = self.store / helper._v2_name(kind, "assignment-one" if kind == "assignment" else "review-one")
            original = path.read_text()
            doc = json.loads(original)
            doc["extra"] = "tampered"
            path.write_text(json.dumps(doc))
            self.assertNotEqual(self.run_cli("verify-review-receipt").returncode, 0)
            path.write_text(original)

    def test_private_symlink_fifo_and_oversize_inputs(self):
        self.assertEqual(self.assign().returncode, 0)
        self.report.chmod(0o644)
        self.assertNotEqual(self.write().returncode, 0)
        self.report.chmod(0o600)
        external = self.root / "external"
        self.report.rename(external)
        self.report.symlink_to(external)
        self.assertNotEqual(self.write().returncode, 0)
        self.report.unlink()
        os.mkfifo(self.report, mode=0o600)
        self.assertNotEqual(self.write().returncode, 0)
        self.report.unlink()
        self.report.write_text("x" * (helper.MAX_REPORT_BYTES + 1))
        self.report.chmod(0o600)
        self.assertNotEqual(self.write().returncode, 0)

    def test_malformed_and_duplicate_json_rejected(self):
        self.assertEqual(self.assign().returncode, 0)
        for text in ['{"verdict":"APPROVE","verdict":"BLOCK"}', '{"x":NaN}', '[]', '{"verdict":true}']:
            self.report.write_text(text)
            self.assertNotEqual(self.write().returncode, 0)

    def test_busy_store_is_bounded_and_private_artifacts_required(self):
        self.prepared()
        with (self.store / "review-v2.lock").open("r+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            self.assertNotEqual(self.run_cli("verify-review").returncode, 0)
        path = self.store / helper._v2_name("report", "review-one")
        path.chmod(0o644)
        self.assertNotEqual(self.run_cli("verify-review").returncode, 0)


if __name__ == "__main__":
    unittest.main()
