#!/usr/bin/env python3
"""Behavior checks for the exact-head, change-aware PR evidence helper."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECK_PR = ROOT / "scripts/check-pr.sh"
PR_EVIDENCE = ROOT / "scripts/pr-evidence.py"


class CheckPrTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.project = self.root / "project"
        (self.project / "scripts").mkdir(parents=True)
        shutil.copy2(CHECK_PR, self.project / "scripts/check-pr.sh")
        shutil.copy2(PR_EVIDENCE, self.project / "scripts/pr-evidence.py")
        (self.project / "scripts/validate-release.sh").write_text(
            "#!/bin/sh\nset -eu\nprintf '%s\\n' 'fixture validation passed'\n",
            encoding="utf-8",
        )
        (self.project / "scripts/validate-release.sh").chmod(0o755)
        (self.project / "README.md").write_text("check-pr fixture\n", encoding="utf-8")
        self.git("init", "-b", "main")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "user.name", "Check PR Test")
        self.git("add", ".")
        self.git("commit", "-m", "prepare check-pr fixture")
        self.base = self.git("rev-parse", "HEAD")

    def git(self, *args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(self.project), *args],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return result.stdout.strip()

    def commit_file(self, relative: str, content: str) -> str:
        path = self.project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-m", f"change {relative}")
        return self.git("rev-parse", "HEAD")

    def run_check(
        self,
        head: str | None = None,
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        if extra_env:
            env.update(extra_env)
        candidate = head or self.git("rev-parse", "HEAD")
        return subprocess.run(
            ["sh", str(self.project / "scripts/check-pr.sh"), self.base, candidate],
            cwd=self.project,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
            check=False,
        )

    def test_docs_report_exact_commits_and_ready_status(self) -> None:
        head = self.commit_file("docs/guide.md", "documentation\n")

        result = self.run_check(head)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(f"Base commit: {self.base}", result.stdout)
        self.assertIn(f"Candidate commit: {head}", result.stdout)
        self.assertIn("Categories: documentation", result.stdout)
        self.assertIn("Full repository validation", result.stdout)
        self.assertIn("Result: PASS", result.stdout)
        self.assertIn("OpenWrt integration: not required", result.stdout)
        self.assertIn("CHECK_PR_RESULT=READY_FOR_REVIEW", result.stdout)

    def test_machine_evidence_is_exact_deterministic_and_secret_free(self) -> None:
        head = self.commit_file("docs/guide.md", "documentation\n")
        evidence = Path(self.temp.name) / "pr-evidence.json"
        result = self.run_check(
            head,
            {
                "PR_EVIDENCE_PATH": str(evidence),
                "GITHUB_RUN_ID": "123456",
                "GITHUB_RUN_ATTEMPT": "2",
                "GITHUB_WORKFLOW": "PR evidence",
                "GITHUB_EVENT_NAME": "pull_request",
                "GITHUB_TOKEN": "PR_EVIDENCE_SECRET_SENTINEL",
            },
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        first_bytes = evidence.read_bytes()
        document = json.loads(first_bytes)
        self.assertEqual(document["schema_version"], 1)
        self.assertEqual(document["candidate"]["base_sha"], self.base)
        self.assertEqual(document["candidate"]["candidate_sha"], head)
        self.assertEqual(document["candidate"]["changed_files"], ["docs/guide.md"])
        self.assertEqual(document["candidate"]["categories"], ["documentation"])
        self.assertEqual(document["result"], "READY_FOR_REVIEW")
        self.assertEqual(document["ci"]["run_id"], "123456")
        self.assertTrue(any(item["name"] == "Full repository validation" for item in document["checks"]))
        self.assertNotIn("PR_EVIDENCE_SECRET_SENTINEL", first_bytes.decode("utf-8"))

        rerun = self.run_check(
            head,
            {
                "PR_EVIDENCE_PATH": str(evidence),
                "GITHUB_RUN_ID": "123456",
                "GITHUB_RUN_ATTEMPT": "2",
                "GITHUB_WORKFLOW": "PR evidence",
                "GITHUB_EVENT_NAME": "pull_request",
            },
        )
        self.assertEqual(rerun.returncode, 0, rerun.stdout)
        self.assertEqual(evidence.read_bytes(), first_bytes)

    def test_machine_evidence_preserves_blocked_manual_gates_and_skips(self) -> None:
        head = self.commit_file(
            "luci-app-xray-mitm/htdocs/example.js",
            "const example = 1;\n",
        )
        evidence = Path(self.temp.name) / "blocked-evidence.json"
        result = self.run_check(
            head,
            {
                "PR_EVIDENCE_PATH": str(evidence),
                "NODE_BIN": "/path/that/does/not/exist",
            },
        )

        self.assertNotEqual(result.returncode, 0)
        document = json.loads(evidence.read_text(encoding="utf-8"))
        self.assertEqual(document["result"], "BLOCKED")
        gates = {item["type"]: item for item in document["manual_gates"]}
        self.assertEqual(gates["openwrt_integration"]["status"], "required")
        self.assertEqual(gates["ax4200_browser"]["status"], "required")
        self.assertFalse(gates["ax4200_browser"]["performed"])
        self.assertTrue(any(item["result"] == "SKIPPED" for item in document["checks"]))

        ci_evidence = Path(self.temp.name) / "ci-blocked-evidence.json"
        ci_result = self.run_check(
            head,
            {
                "PR_EVIDENCE_PATH": str(ci_evidence),
                "NODE_BIN": "/path/that/does/not/exist",
                "CHECK_PR_ALLOW_MANUAL_GATES": "1",
            },
        )
        self.assertEqual(ci_result.returncode, 0, ci_result.stdout)
        ci_document = json.loads(ci_evidence.read_text(encoding="utf-8"))
        self.assertEqual(ci_document["result"], "BLOCKED")

    def test_shell_changes_receive_focused_syntax_check(self) -> None:
        head = self.commit_file("scripts/changed.sh", "#!/bin/sh\nprintf '%s\\n' ok\n")

        result = self.run_check(head)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("Focused shell syntax: scripts/changed.sh", result.stdout)
        self.assertIn("CHECK_PR_RESULT=READY_FOR_REVIEW", result.stdout)

    def test_failed_command_output_is_not_echoed(self) -> None:
        sentinel = "CHECK_PR_FIXTURE_SECRET_SENTINEL"
        (self.project / "scripts/validate-release.sh").write_text(
            f"#!/bin/sh\nprintf '%s\\n' '{sentinel}'\nexit 23\n",
            encoding="utf-8",
        )
        head = self.commit_file("docs/guide.md", "documentation\n")

        result = self.run_check(head)

        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn(sentinel, result.stdout)
        self.assertIn("command output suppressed", result.stdout)
        self.assertIn("CHECK_PR_RESULT=FAILED", result.stdout)

    def test_post_validation_dirty_state_is_not_reported_ready(self) -> None:
        (self.project / "scripts/validate-release.sh").write_text(
            "#!/bin/sh\nprintf '%s\\n' mutation > post-validation-marker\n",
            encoding="utf-8",
        )
        head = self.commit_file("docs/guide.md", "documentation\n")

        result = self.run_check(head)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Post-validation working-tree check: FAIL", result.stdout)
        self.assertIn("CHECK_PR_RESULT=FAILED", result.stdout)

    def test_post_validation_head_change_is_not_reported_ready(self) -> None:
        (self.project / "scripts/validate-release.sh").write_text(
            "#!/bin/sh\ngit commit --allow-empty -m validator-moved-head >/dev/null\n",
            encoding="utf-8",
        )
        head = self.commit_file("docs/guide.md", "documentation\n")

        result = self.run_check(head)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Post-validation HEAD check: FAIL", result.stdout)
        self.assertIn("CHECK_PR_RESULT=FAILED", result.stdout)

    def test_frontend_changes_block_without_node_and_manual_gates(self) -> None:
        head = self.commit_file(
            "luci-app-xray-mitm/htdocs/example.js",
            "const example = 1;\n",
        )

        result = self.run_check(head, {"NODE_BIN": "/path/that/does/not/exist"})

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Focused frontend checks: SKIPPED", result.stdout)
        self.assertIn("OpenWrt integration: REQUIRED", result.stdout)
        self.assertIn("AX4200/browser validation: REQUIRED", result.stdout)
        self.assertIn("CHECK_PR_RESULT=BLOCKED", result.stdout)

    def test_passwall_changes_run_focus_and_block_for_router_gate(self) -> None:
        self.project.joinpath("tests").mkdir()
        (self.project / "tests/test_passwall2.py").write_text(
            "print('fixture PassWall2 test')\n", encoding="utf-8"
        )
        self.git("add", "tests/test_passwall2.py")
        self.git("commit", "-m", "add fixture PassWall2 test")
        self.base = self.git("rev-parse", "HEAD")
        head = self.commit_file(
            "xray-mitm/files/usr/libexec/xray-mitm/passwall2",
            "#!/bin/sh\nprintf '%s\\n' passwall\n",
        )

        result = self.run_check(head)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Focused PassWall2 tests", result.stdout)
        self.assertIn("Result: PASS", result.stdout)
        self.assertIn("OpenWrt integration: REQUIRED", result.stdout)
        self.assertIn("CHECK_PR_RESULT=BLOCKED", result.stdout)

    def test_router_dns_fallback_changes_run_focus_and_block_for_openwrt_gate(self) -> None:
        (self.project / "tests").mkdir()
        (self.project / "tests/test_router_dns_fallback.py").write_text(
            "print('fixture router DNS fallback test')\n", encoding="utf-8"
        )
        self.git("add", "tests/test_router_dns_fallback.py")
        self.git("commit", "-m", "add fixture router DNS fallback test")
        self.base = self.git("rev-parse", "HEAD")
        head = self.commit_file(
            "scripts/router-dns-fallback.sh",
            "#!/bin/sh\nprintf '%s\\n' router-dns-fallback\n",
        )

        result = self.run_check(head)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Focused router-DNS fallback tests", result.stdout)
        self.assertIn("Result: PASS", result.stdout)
        self.assertIn("OpenWrt integration: REQUIRED", result.stdout)
        self.assertIn("AX4200/browser validation: not required", result.stdout)
        self.assertIn("CHECK_PR_RESULT=BLOCKED", result.stdout)

    def test_dirty_checkout_is_rejected_before_evidence(self) -> None:
        self.commit_file("docs/guide.md", "documentation\n")
        (self.project / "untracked.txt").write_text("uncommitted\n", encoding="utf-8")

        result = self.run_check()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("candidate checkout is not clean", result.stdout)
        self.assertIn("CHECK_PR_RESULT=BLOCKED", result.stdout)

    def test_candidate_must_match_current_checkout_head(self) -> None:
        self.commit_file("docs/guide.md", "documentation\n")

        result = self.run_check(self.base)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("checkout HEAD", result.stdout)
        self.assertIn("CHECK_PR_RESULT=BLOCKED", result.stdout)

    def test_unknown_changed_path_is_fail_closed(self) -> None:
        head = self.commit_file("mystery.bin", "unknown\n")

        result = self.run_check(head)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Categories: unknown", result.stdout)
        self.assertIn("no validation mapping", result.stdout)
        self.assertIn("CHECK_PR_RESULT=BLOCKED", result.stdout)


if __name__ == "__main__":
    unittest.main()
