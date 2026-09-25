#!/usr/bin/env python3
"""Tests for durable, local-only Work report handoff artifacts."""

from __future__ import annotations

import json
import errno
import importlib.util
import os
import stat
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts/work-report-handoff.py"
SOURCE = "11111111-1111-4111-8111-111111111111"
DESTINATION = "22222222-2222-4222-8222-222222222222"
CANDIDATE = "a" * 40
TURN = "33333333-3333-4333-8333-333333333333"


class WorkReportHandoffTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / "repo"
        self.repo.mkdir()
        subprocess.run(
            ["git", "-C", str(self.repo), "init", "-b", "main"],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        self.report = Path(self.temp.name) / "report.md"
        self.report.write_text("Recommendation: APPROVE\nEvidence: bounded review\n", encoding="utf-8")

    def run_helper(self, command: str, *extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "python3",
                str(HELPER),
                command,
                "--repo",
                str(self.repo),
                "--source-task-id",
                SOURCE,
                "--destination-task-id",
                DESTINATION,
                "--report-id",
                "pr-72-review",
                *extra,
            ],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
        )

    def write(self) -> subprocess.CompletedProcess[str]:
        return self.run_helper(
            "write",
            "--title",
            "PR #72 review",
            "--candidate-sha",
            CANDIDATE,
            "--report-file",
            str(self.report),
        )

    def artifact(self) -> Path:
        return self.repo / ".codex" / "handoffs" / DESTINATION / "pr-72-review.json"

    def run_final_helper(self, sessions: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["python3", str(HELPER), "read-final", "--sessions-root", str(sessions),
             "--source-task-id", SOURCE, "--turn-id", TURN],
            check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=5,
        )

    def test_read_exact_completed_turn_including_separate_note(self) -> None:
        sessions = Path(self.temp.name) / "sessions"
        log_dir = sessions / "2026" / "09" / "25"
        log_dir.mkdir(parents=True)
        log = log_dir / f"rollout-2026-09-25T12-00-00-{SOURCE}.jsonl"
        records = [
            {"type": "event_msg", "payload": {"type": "task_complete", "turn_id": DESTINATION,
                                              "last_agent_message": "Unrelated final"}},
            {"timestamp": "2026-09-25T08:33:14Z", "type": "event_msg",
             "payload": {"type": "task_complete", "turn_id": TURN,
                         "last_agent_message": "Separate note: PR #73 was unrelated.\nPR #46 review follows."}},
        ]
        log.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
        result = self.run_final_helper(sessions)
        self.assertEqual(result.returncode, 0, result.stderr)
        final = json.loads(result.stdout)
        self.assertEqual(final["turn_id"], TURN)
        self.assertIn("Separate note", final["final_message"])
        self.assertEqual(final["completed_at"], "2026-09-25T08:33:14Z")

    def test_read_final_fails_closed_on_missing_or_duplicate_completion(self) -> None:
        sessions = Path(self.temp.name) / "sessions"
        log_dir = sessions / "2026" / "09" / "25"
        log_dir.mkdir(parents=True)
        log = log_dir / f"rollout-2026-09-25T12-00-00-{SOURCE}.jsonl"
        self.assertNotEqual(self.run_final_helper(sessions).returncode, 0)
        record = {"timestamp": "2026-09-25T08:33:14Z", "type": "event_msg",
                  "payload": {"type": "task_complete", "turn_id": TURN,
                              "last_agent_message": "Report"}}
        log.write_text((json.dumps(record) + "\n") * 2, encoding="utf-8")
        self.assertNotEqual(self.run_final_helper(sessions).returncode, 0)

    def test_read_final_rejects_symlinked_log(self) -> None:
        sessions = Path(self.temp.name) / "sessions"
        log_dir = sessions / "2026" / "09" / "25"
        log_dir.mkdir(parents=True)
        target = Path(self.temp.name) / "elsewhere.jsonl"
        target.write_text("", encoding="utf-8")
        (log_dir / f"rollout-2026-09-25T12-00-00-{SOURCE}.jsonl").symlink_to(target)
        self.assertNotEqual(self.run_final_helper(sessions).returncode, 0)

    def test_write_verify_and_read_round_trip(self) -> None:
        written = self.write()
        self.assertEqual(written.returncode, 0, written.stderr)
        receipt = json.loads(written.stdout)
        self.assertEqual(receipt["source_task_id"], SOURCE)
        self.assertEqual(receipt["destination_task_id"], DESTINATION)
        self.assertEqual(receipt["candidate_sha"], CANDIDATE)
        self.assertRegex(receipt["handoff_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(receipt["artifact"], f".codex/handoffs/{DESTINATION}/pr-72-review.json")

        artifact = self.artifact()
        self.assertTrue(artifact.is_file())
        self.assertEqual(stat.S_IMODE(artifact.stat().st_mode), 0o600)

        verified = self.run_helper("verify", "--candidate-sha", CANDIDATE)
        self.assertEqual(verified.returncode, 0, verified.stderr)
        self.assertEqual(json.loads(verified.stdout), receipt)

        read = self.run_helper("read", "--candidate-sha", CANDIDATE)
        self.assertEqual(read.returncode, 0, read.stderr)
        self.assertEqual(read.stdout, self.report.read_text(encoding="utf-8"))

    def test_artifact_is_immutable(self) -> None:
        self.assertEqual(self.write().returncode, 0)
        repeated = self.write()
        self.assertNotEqual(repeated.returncode, 0)
        self.assertIn("will not be overwritten", repeated.stderr)

    def test_self_target_is_rejected(self) -> None:
        result = subprocess.run(
            [
                "python3",
                str(HELPER),
                "write",
                "--repo",
                str(self.repo),
                "--source-task-id",
                SOURCE,
                "--destination-task-id",
                SOURCE,
                "--report-id",
                "self-target",
                "--title",
                "invalid",
                "--report-file",
                str(self.report),
            ],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must differ", result.stderr)

    def test_tampering_is_detected(self) -> None:
        self.assertEqual(self.write().returncode, 0)
        document = json.loads(self.artifact().read_text(encoding="utf-8"))
        document["report"] = "changed after delivery\n"
        self.artifact().write_text(json.dumps(document), encoding="utf-8")
        os.chmod(self.artifact(), 0o600)
        verified = self.run_helper("verify")
        self.assertNotEqual(verified.returncode, 0)
        self.assertIn("report hash does not match", verified.stderr)

    def test_candidate_mismatch_and_metadata_tampering_are_detected(self) -> None:
        self.assertEqual(self.write().returncode, 0)
        mismatch = self.run_helper("verify", "--candidate-sha", "b" * 40)
        self.assertNotEqual(mismatch.returncode, 0)
        self.assertIn("candidate SHA does not match", mismatch.stderr)

        document = json.loads(self.artifact().read_text(encoding="utf-8"))
        document["candidate_sha"] = "b" * 40
        self.artifact().write_text(json.dumps(document), encoding="utf-8")
        os.chmod(self.artifact(), 0o600)
        tampered = self.run_helper("verify")
        self.assertNotEqual(tampered.returncode, 0)
        self.assertIn("content hash does not match", tampered.stderr)

    def test_verify_missing_artifact_is_read_only(self) -> None:
        verified = self.run_helper("verify")
        self.assertNotEqual(verified.returncode, 0)
        self.assertIn("does not exist", verified.stderr)
        self.assertFalse((self.repo / ".codex" / "handoffs").exists())

    def test_symlink_artifact_and_broad_parent_permissions_fail_closed(self) -> None:
        self.assertEqual(self.write().returncode, 0)
        artifact = self.artifact()
        artifact.unlink()
        artifact.symlink_to(self.report)
        linked = self.run_helper("read")
        self.assertNotEqual(linked.returncode, 0)
        self.assertIn("opened safely", linked.stderr)

        artifact.unlink()
        self.assertEqual(self.write().returncode, 0)
        os.chmod(artifact.parent, 0o755)
        broad = self.run_helper("verify")
        self.assertNotEqual(broad.returncode, 0)
        self.assertIn("directory permissions are too broad", broad.stderr)

    def test_symlinked_handoff_directory_is_rejected(self) -> None:
        codex = self.repo / ".codex"
        codex.mkdir(mode=0o700)
        external = Path(self.temp.name) / "external"
        external.mkdir()
        (codex / "handoffs").symlink_to(external, target_is_directory=True)
        result = self.write()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("opened safely", result.stderr)

    def test_fifo_artifact_fails_without_blocking(self) -> None:
        artifact = self.artifact()
        artifact.parent.mkdir(mode=0o700, parents=True)
        os.chmod(artifact.parent, 0o700)
        os.chmod(artifact.parent.parent, 0o700)
        os.mkfifo(artifact, mode=0o600)
        result = self.run_helper("verify", "--candidate-sha", CANDIDATE)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must be a regular file", result.stderr)

    def test_repository_root_replacement_fails_before_artifact_creation(self) -> None:
        report_fifo = Path(self.temp.name) / "report-fifo"
        os.mkfifo(report_fifo, mode=0o600)
        process = subprocess.Popen(
            [
                "python3",
                str(HELPER),
                "write",
                "--repo",
                str(self.repo),
                "--source-task-id",
                SOURCE,
                "--destination-task-id",
                DESTINATION,
                "--report-id",
                "root-race",
                "--title",
                "root race",
                "--candidate-sha",
                CANDIDATE,
                "--report-file",
                str(report_fifo),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        writer_fd: int | None = None
        deadline = time.monotonic() + 5
        try:
            while writer_fd is None and time.monotonic() < deadline:
                try:
                    writer_fd = os.open(report_fifo, os.O_WRONLY | os.O_NONBLOCK)
                except OSError as exc:
                    if exc.errno != errno.ENXIO:
                        raise
                    if process.poll() is not None:
                        self.fail("helper exited before opening the report FIFO")
                    time.sleep(0.01)
            self.assertIsNotNone(writer_fd, "helper did not reach the report FIFO")

            moved_repo = Path(self.temp.name) / "repo-moved"
            self.repo.rename(moved_repo)
            self.repo.mkdir()
            os.write(writer_fd, b"Recommendation: APPROVE\n")
            os.close(writer_fd)
            writer_fd = None
            stdout, stderr = process.communicate(timeout=5)
        finally:
            if writer_fd is not None:
                os.close(writer_fd)
            if process.poll() is None:
                process.kill()
                process.communicate()

        self.assertNotEqual(process.returncode, 0, stdout)
        self.assertIn("repository path changed", stderr)
        relative = Path(".codex") / "handoffs" / DESTINATION / "root-race.json"
        self.assertFalse((moved_repo / relative).exists())
        self.assertFalse((self.repo / relative).exists())

    def test_repository_root_replacement_after_link_removes_artifact(self) -> None:
        spec = importlib.util.spec_from_file_location("work_report_handoff", HELPER)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)

        relative = Path(".codex") / "handoffs" / DESTINATION / "late-root-race.json"
        moved_repo = Path(self.temp.name) / "repo-moved-late"
        original_assert = helper._assert_repo_path

        def replace_root_after_link(repo: Path, repo_fd: int) -> None:
            if not moved_repo.exists() and (repo / relative).exists():
                repo.rename(moved_repo)
                self.repo.mkdir()
            original_assert(repo, repo_fd)

        helper._assert_repo_path = replace_root_after_link
        args = SimpleNamespace(
            repo=self.repo,
            source_task_id=SOURCE,
            destination_task_id=DESTINATION,
            report_id="late-root-race",
            candidate_sha=CANDIDATE,
            title="late root race",
            report_file=str(self.report),
        )
        with self.assertRaisesRegex(helper.HandoffError, "repository path changed"):
            helper.write(args)

        self.assertFalse((moved_repo / relative).exists())
        self.assertFalse((self.repo / relative).exists())


if __name__ == "__main__":
    unittest.main()
