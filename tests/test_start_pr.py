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
        self.real_git = shutil.which("git")
        if self.real_git is None:
            raise unittest.SkipTest("git is required for start-pr tests")
        self.worktrees.mkdir()
        (self.project / "scripts").mkdir(parents=True)
        (self.project / "docs/ai").mkdir(parents=True)
        (self.root / "fake-bin").mkdir()
        shutil.copy2(START_PR, self.project / "scripts/start-pr.sh")
        shutil.copy2(ROOT / "scripts/verify-roadmap-state.sh", self.project / "scripts/verify-roadmap-state.sh")
        shutil.copy2(ROOT / "scripts/verify-github-remote.sh", self.project / "scripts/verify-github-remote.sh")

        (self.project / "README.md").write_text("start-pr fixture\n", encoding="utf-8")
        self.git("init", "-b", "main")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "user.name", "Start PR Test")
        self.git("add", "README.md", "scripts/start-pr.sh", "scripts/verify-roadmap-state.sh", "scripts/verify-github-remote.sh")
        self.git("commit", "-m", "prepare start-pr fixture")
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
        env.update(self.failing_git_env(""))
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

    def failing_git_env(self, failure: str, mock_effective_urls: bool = True) -> dict[str, str]:
        fake_bin = self.root / "fake-bin"
        fake_bin.mkdir(exist_ok=True)
        fake_git = fake_bin / "git"
        fake_git.write_text(
            """#!/bin/sh
set -eu

real_git=${START_PR_REAL_GIT:?}
failure=${START_PR_FAIL_GIT-}
saw_worktree=0
saw_list=0
saw_remote=0
saw_get_url=0
saw_push=0

for arg in "$@"; do
    [ "$arg" = worktree ] && saw_worktree=1
    [ "$arg" = list ] && saw_list=1
    [ "$arg" = remote ] && saw_remote=1
    [ "$arg" = get-url ] && saw_get_url=1
    [ "$arg" = --push ] && saw_push=1
done

if [ "$saw_remote" -eq 1 ] && [ "$saw_get_url" -eq 1 ] && [ "${START_PR_MOCK_EFFECTIVE_URLS:-1}" = 1 ]; then
    printf '%s\\n' 'https://github.com/duuuude/xray-mitm-openwrt.git'
    exit 0
fi

case "$failure" in
    status)
        for arg in "$@"; do
            [ "$arg" = status ] && exit 42
        done
        ;;
    worktree-list)
        [ "$saw_worktree" -eq 1 ] && [ "$saw_list" -eq 1 ] && exit 42
        ;;
    show-ref)
        for arg in "$@"; do
            [ "$arg" = show-ref ] && exit 42
        done
        ;;
esac

exec "$real_git" "$@"
""",
            encoding="utf-8",
        )
        fake_git.chmod(0o755)
        return {
            "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
            "START_PR_FAIL_GIT": failure,
            "START_PR_REAL_GIT": self.real_git,
            "START_PR_MOCK_EFFECTIVE_URLS": "1" if mock_effective_urls else "0",
        }

    def test_success_fast_forwards_clean_main_and_creates_worktree(self) -> None:
        (self.project / "README.md").write_text("remote update\n", encoding="utf-8")
        self.git("add", "README.md")
        self.git("commit", "-m", "advance remote main")
        baseline = self.git("rev-parse", "HEAD")
        (self.project / "docs/ai/MASTER_PLAN.md").write_text(
            f"# Fixture plan\n\n- Review/audit baseline: `{baseline}`, fixture main\n",
            encoding="utf-8",
        )
        self.git("add", "docs/ai/MASTER_PLAN.md")
        self.git("commit", "-m", "reconcile remote update")
        self.git("push", "origin", "main")
        self.git("reset", "--hard", "HEAD^^")

        result = self.run_start_pr()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Base branch: main", result.stdout)
        self.assertIn("Feature branch: feat/example", result.stdout)
        self.assertIn(f"Worktree: {self.worktrees / 'example'}", result.stdout)
        self.assertEqual(self.git("branch", "--show-current"), "main")
        self.assertEqual(self.git("rev-parse", "HEAD"), self.git("rev-parse", "origin/main"))
        self.assertTrue((self.worktrees / "example" / "README.md").exists())
        self.assertTrue(self.ref_exists("refs/heads/feat/example"))

    def test_rejects_untracked_main_before_fetch(self) -> None:
        (self.project / "untracked.txt").write_text("unique\n", encoding="utf-8")

        result = self.run_start_pr()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("main checkout is not clean", result.stderr)
        self.assertFalse(self.ref_exists("refs/heads/feat/example"))

    def test_rejects_tracked_dirty_main_before_fetch(self) -> None:
        (self.project / "README.md").write_text("tracked change\n", encoding="utf-8")

        result = self.run_start_pr()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("main checkout is not clean", result.stderr)
        self.assertFalse(self.ref_exists("refs/heads/feat/example"))

    def test_rejects_stale_roadmap_after_main_is_synchronized(self) -> None:
        remote_clone = self.root / "remote-clone"
        subprocess.run(
            ["git", "clone", "--branch", "main", str(self.remote), str(remote_clone)],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.git_at(remote_clone, "config", "user.email", "remote@example.invalid")
        self.git_at(remote_clone, "config", "user.name", "Remote Main")
        (remote_clone / "README.md").write_text("unreconciled remote\n", encoding="utf-8")
        self.git_at(remote_clone, "add", "README.md")
        self.git_at(remote_clone, "commit", "-m", "unreconciled main implementation")
        self.git_at(remote_clone, "push", "origin", "main")
        self.git("fetch", "origin", "main")
        self.git("merge", "--ff-only", "origin/main")

        result = self.run_start_pr()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ROADMAP_STATE=STALE", result.stderr)
        self.assertIn("unreconciled main implementation", result.stderr)
        self.assertFalse(self.ref_exists("refs/heads/feat/example"))
        self.assertFalse((self.worktrees / "example").exists())

    def test_rejects_insteadof_redirect_before_fetch_or_worktree_creation(self) -> None:
        old_main = self.git("rev-parse", "refs/heads/main")
        old_tracking = self.git("rev-parse", "refs/remotes/origin/main")
        rogue = self.root / "rogue.git"
        subprocess.run(["git", "init", "--bare", str(rogue)], check=True, capture_output=True, text=True)
        clone = self.root / "rogue-clone"
        subprocess.run(["git", "clone", "--branch", "main", str(self.remote), str(clone)], check=True, capture_output=True, text=True)
        self.git_at(clone, "config", "user.email", "rogue@example.invalid")
        self.git_at(clone, "config", "user.name", "Rogue Mirror")
        (clone / "README.md").write_text("unapproved source\n", encoding="utf-8")
        self.git_at(clone, "add", "README.md")
        self.git_at(clone, "commit", "-m", "rogue main update")
        self.git_at(clone, "remote", "set-url", "origin", str(rogue))
        self.git_at(clone, "push", "origin", "main")
        self.git("config", "--unset-all", f"url.{self.remote}.insteadOf")
        self.git("config", f"url.{rogue}.insteadOf", CANONICAL_URL)

        result = self.run_start_pr(extra_env=self.failing_git_env("", mock_effective_urls=False))

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Effective fetch URL", result.stderr)
        self.assertEqual(self.git("rev-parse", "refs/heads/main"), old_main)
        self.assertEqual(self.git("rev-parse", "refs/remotes/origin/main"), old_tracking)
        self.assertFalse(self.ref_exists("refs/heads/feat/example"))
        self.assertFalse((self.worktrees / "example").exists())

    def test_rejects_missing_roadmap_contract(self) -> None:
        self.git("rm", "docs/ai/MASTER_PLAN.md")
        self.git("commit", "-m", "remove roadmap contract")
        self.git("push", "origin", "main")
        self.git("reset", "--hard", "HEAD^")

        result = self.run_start_pr()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Required docs/ai/MASTER_PLAN.md is missing", result.stderr)
        self.assertFalse(self.ref_exists("refs/heads/feat/example"))

    def test_rejects_git_status_inspection_failure(self) -> None:
        result = self.run_start_pr(extra_env=self.failing_git_env("status"))

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Could not inspect the canonical main status", result.stderr)
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

    def test_accepts_a_logical_alias_for_the_physical_worktrees_root(self) -> None:
        logical_root = self.root / "logical-workspace"
        logical_root.symlink_to(self.root, target_is_directory=True)
        target = logical_root / "worktrees" / "alias-example"

        result = self.run_start_pr(path=target)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue((self.worktrees / "alias-example" / "README.md").exists())

    def test_rejects_a_symlinked_worktrees_root(self) -> None:
        escaped_root = self.root / "escaped-worktrees"
        escaped_root.mkdir()
        self.worktrees.rmdir()
        self.worktrees.symlink_to(escaped_root, target_is_directory=True)

        result = self.run_start_pr()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("worktrees root must not be a symlink", result.stderr)
        self.assertFalse(self.ref_exists("refs/heads/feat/example"))
        self.assertFalse((escaped_root / "example").exists())

    def test_rejects_git_worktree_list_inspection_failure(self) -> None:
        result = self.run_start_pr(extra_env=self.failing_git_env("worktree-list"))

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Could not inspect registered worktrees", result.stderr)
        self.assertFalse(self.ref_exists("refs/heads/feat/example"))

    def test_rejects_git_show_ref_inspection_failure(self) -> None:
        result = self.run_start_pr(extra_env=self.failing_git_env("show-ref"))

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Could not inspect local branch references", result.stderr)
        self.assertFalse(self.ref_exists("refs/heads/feat/example"))

    def test_rejects_local_ahead_main_without_overwriting(self) -> None:
        (self.project / "README.md").write_text("unique local\n", encoding="utf-8")
        self.git("add", "README.md")
        self.git("commit", "-m", "unique local main work")

        result = self.run_start_pr()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ahead of or diverged", result.stderr)
        self.assertFalse(self.ref_exists("refs/heads/feat/example"))

    def test_rejects_diverged_main_without_overwriting(self) -> None:
        (self.project / "README.md").write_text("unique local\n", encoding="utf-8")
        self.git("add", "README.md")
        self.git("commit", "-m", "unique local main work")

        remote_clone = self.root / "remote-clone"
        subprocess.run(
            ["git", "clone", "--branch", "main", str(self.remote), str(remote_clone)],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.git_at(remote_clone, "config", "user.email", "remote@example.invalid")
        self.git_at(remote_clone, "config", "user.name", "Remote Main")
        (remote_clone / "README.md").write_text("unique remote\n", encoding="utf-8")
        self.git_at(remote_clone, "add", "README.md")
        self.git_at(remote_clone, "commit", "-m", "unique remote main work")
        self.git_at(remote_clone, "push", "origin", "main")

        local_before = self.git("rev-parse", "HEAD")
        result = self.run_start_pr()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ahead of or diverged", result.stderr)
        self.assertEqual(self.git("rev-parse", "HEAD"), local_before)
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
