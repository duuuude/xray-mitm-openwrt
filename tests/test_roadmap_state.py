#!/usr/bin/env python3
"""Behavior checks for roadmap/current-main reconciliation."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERIFY = ROOT / "scripts/verify-roadmap-state.sh"
CANONICAL_URL = "https://github.com/duuuude/xray-mitm-openwrt.git"


class RoadmapStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name).resolve()
        self.project = root / "project"
        self.remote = root / "remote.git"
        (self.project / "scripts").mkdir(parents=True)
        (self.project / "docs/ai").mkdir(parents=True)
        shutil.copy2(VERIFY, self.project / "scripts/verify-roadmap-state.sh")

        (self.project / "README.md").write_text("roadmap fixture\n", encoding="utf-8")
        self.git("init", "-b", "main")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "user.name", "Roadmap State Test")
        self.git("add", "README.md", "scripts/verify-roadmap-state.sh")
        self.git("commit", "-m", "prepare roadmap fixture")
        baseline = self.git("rev-parse", "HEAD")
        (self.project / "docs/ai/MASTER_PLAN.md").write_text(
            f"# Fixture plan\n\n- Review/audit baseline: `{baseline}`, fixture main\n",
            encoding="utf-8",
        )
        self.git("add", "docs/ai/MASTER_PLAN.md")
        self.git("commit", "-m", "reconcile fixture roadmap")

        subprocess.run(
            ["git", "init", "--bare", str(self.remote)],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.git("remote", "add", "origin", CANONICAL_URL)
        self.git("config", f"url.{self.remote}.insteadOf", CANONICAL_URL)
        self.git("push", "-u", "origin", "main")

    def git(self, *args: str) -> str:
        return self.git_at(self.project, *args)

    def git_at(self, directory: Path, *args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(directory), *args],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return result.stdout.strip()

    def run_verify(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["sh", str(self.project / "scripts/verify-roadmap-state.sh"), "origin"],
            cwd=self.project,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def test_accepts_reconciled_plan_only_head(self) -> None:
        result = self.run_verify()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("ROADMAP_STATE=READY", result.stdout)
        self.assertIn("Audit relation: plan-only-head-parent", result.stdout)
        self.assertIn("reconcile fixture roadmap", result.stdout)

    def test_blocks_new_main_commit_until_plan_is_reconciled(self) -> None:
        (self.project / "README.md").write_text("new main behavior\n", encoding="utf-8")
        self.git("add", "README.md")
        self.git("commit", "-m", "new implementation not in roadmap")
        self.git("push", "origin", "main")
        self.git("fetch", "origin", "main")

        result = self.run_verify()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ROADMAP_STATE=STALE", result.stderr)
        self.assertIn("Recent first-parent main history", result.stderr)
        self.assertIn("new implementation not in roadmap", result.stderr)

    def test_blocks_dirty_main_before_planning(self) -> None:
        (self.project / "README.md").write_text("uncommitted\n", encoding="utf-8")

        result = self.run_verify()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("main checkout is not clean", result.stderr)

    def test_refreshes_remote_and_blocks_unreconciled_main(self) -> None:
        remote_clone = Path(self.temp.name) / "remote-clone"
        subprocess.run(
            ["git", "clone", "--branch", "main", str(self.remote), str(remote_clone)],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.git_at(remote_clone, "config", "user.email", "remote@example.invalid")
        self.git_at(remote_clone, "config", "user.name", "Remote Main")
        clone_readme = Path(remote_clone) / "README.md"
        clone_readme.write_text("unreconciled remote\n", encoding="utf-8")
        self.git_at(remote_clone, "add", "README.md")
        self.git_at(remote_clone, "commit", "-m", "unreconciled remote implementation")
        self.git_at(remote_clone, "push", "origin", "main")
        self.git("fetch", "origin", "main")
        self.git("merge", "--ff-only", "origin/main")
        current_main = self.git("rev-parse", "HEAD")
        self.git("update-ref", "refs/remotes/origin/main", f"{current_main}^")

        result = self.run_verify()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ROADMAP_STATE=STALE", result.stderr)
        self.assertIn("unreconciled remote implementation", result.stderr)
        self.assertEqual(self.git("rev-parse", "origin/main"), current_main)

    def test_blocks_unverified_remote(self) -> None:
        self.git("remote", "set-url", "origin", "https://example.invalid/project.git")

        result = self.run_verify()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not the verified", result.stderr)
        self.assertIn("ROADMAP_STATE=BLOCKED", result.stderr)


if __name__ == "__main__":
    unittest.main()
