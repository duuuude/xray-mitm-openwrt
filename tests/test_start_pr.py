#!/usr/bin/env python3
"""Behavior checks for the safe repository-state and PR-start helper."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
START_PR = ROOT / "scripts/start-pr.sh"
CANONICAL_URL = "https://github.com/duuuude/xray-mitm-openwrt.git"


class StartPrTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.project = self.root / "project"
        self.remote = self.root / "remote.git"
        self.worktrees = self.root / "worktrees"
        self.worktrees.mkdir()
        (self.project / "scripts").mkdir(parents=True)
        shutil.copy2(START_PR, self.project / "scripts/start-pr.sh")

        (self.project / "README.md").write_text("start-pr fixture\n", encoding="utf-8")
        self.git("init", "-b", "main")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "user.name", "Start PR Test")
        self.git("add", "README.md", "scripts/start-pr.sh")
        self.git("commit", "-m", "prepare start-pr fixture")
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
        result = subprocess.run(
            ["git", "-C", str(self.project), *args],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return result.stdout.strip()

    def ref_exists(self, ref: str) -> bool:
        result = subprocess.run(
            ["git", "-C", str(self.project), "show-ref", "--verify", "--quiet", ref],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return result.returncode == 0

    def run_start_pr(
        self,
        branch: str = "feat/example",
        path: Path | None = None,
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        target = path or (self.worktrees / "example")
        env = os.environ.copy()
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            ["sh", str(self.project / "scripts/start-pr.sh"), branch, str(target)],
            cwd=self.project,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            check=False,
        )

    def test_success_fast_forwards_clean_main_and_creates_worktree(self) -> None:
        (self.project / "README.md").write_text("remote update\n", encoding="utf-8")
        self.git("add", "README.md")
        self.git("commit", "-m", "advance remote main")
        self.git("push", "origin", "main")
        self.git("reset", "--hard", "HEAD^")

        result = self.run_start_pr()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Base branch: main", result.stdout)
        self.assertIn("Feature branch: feat/example", result.stdout)
        self.assertIn(f"Worktree: {self.worktrees / 'example'}", result.stdout)
        self.assertEqual(self.git("branch", "--show-current"), "main")
        self.assertEqual(self.git("rev-parse", "HEAD"), self.git("rev-parse", "origin/main"))
        self.assertTrue((self.worktrees / "example" / "README.md").exists())
        self.assertTrue(self.ref_exists("refs/heads/feat/example"))

    def test_rejects_dirty_or_untracked_main_before_fetch(self) -> None:
        (self.project / "untracked.txt").write_text("unique\n", encoding="utf-8")

        result = self.run_start_pr()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("main checkout is not clean", result.stderr)
        self.assertFalse(self.ref_exists("refs/heads/feat/example"))

    def test_rejects_non_main_checkout(self) -> None:
        self.git("switch", "-c", "existing/local")

        result = self.run_start_pr()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must be on main", result.stderr)

    def test_rejects_wrong_remote_before_fetch(self) -> None:
        self.git("remote", "set-url", "origin", "https://example.invalid/project.git")

        result = self.run_start_pr()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("No verified duuuude/xray-mitm-openwrt GitHub remote", result.stderr)
        self.assertNotIn("Could not fetch", result.stderr)

    def test_rejects_ambiguous_verified_remotes_without_override(self) -> None:
        self.git("remote", "add", "github", CANONICAL_URL)

        result = self.run_start_pr()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("More than one verified GitHub remote", result.stderr)

    def test_allows_explicit_verified_remote_override(self) -> None:
        self.git("remote", "add", "github", CANONICAL_URL)
        self.git("fetch", "github", "main")
        self.git("branch", "--set-upstream-to", "github/main", "main")

        result = self.run_start_pr(extra_env={"START_PR_REMOTE": "github"})

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_rejects_local_branch_collision(self) -> None:
        self.git("branch", "feat/example")

        result = self.run_start_pr()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Local branch already exists", result.stderr)

    def test_rejects_remote_branch_collision(self) -> None:
        self.git("push", "origin", "HEAD:refs/heads/feat/example")

        result = self.run_start_pr()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Remote branch already exists", result.stderr)

    def test_rejects_existing_worktree_path(self) -> None:
        target = self.worktrees / "example"
        target.mkdir()

        result = self.run_start_pr(path=target)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Worktree path already exists", result.stderr)

    def test_rejects_path_outside_worktrees(self) -> None:
        result = self.run_start_pr(path=self.root / "outside")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("directly under", result.stderr)

    def test_rejects_ahead_or_diverged_main_without_overwriting(self) -> None:
        (self.project / "README.md").write_text("unique local\n", encoding="utf-8")
        self.git("add", "README.md")
        self.git("commit", "-m", "unique local main work")

        result = self.run_start_pr()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ahead of or diverged", result.stderr)
        self.assertFalse(self.ref_exists("refs/heads/feat/example"))

    def test_rejects_invalid_branch_name(self) -> None:
        result = self.run_start_pr(branch="bad..name")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Invalid feature branch name", result.stderr)

    def test_source_contains_no_destructive_or_publish_commands(self) -> None:
        source = START_PR.read_text(encoding="utf-8")

        self.assertNotIn("git_at push", source)
        self.assertNotIn("git_at reset", source)
        self.assertNotIn("git_at clean", source)
        self.assertNotIn("branch -D", source)
        self.assertNotIn("worktree remove", source)


if __name__ == "__main__":
    unittest.main()
