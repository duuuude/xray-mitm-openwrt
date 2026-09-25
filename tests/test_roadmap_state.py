#!/usr/bin/env python3
"""Behavior checks for roadmap/current-main reconciliation."""

from __future__ import annotations

import shutil
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERIFY = ROOT / "scripts/verify-roadmap-state.sh"
CANONICAL_URL = "https://github.com/duuuude/xray-mitm-openwrt.git"


class RoadmapStateTests(unittest.TestCase):
    def test_protected_release_next_steps_require_a_green_full_validator(self) -> None:
        plan = (ROOT / "docs/ai/MASTER_PLAN.md").read_text(encoding="utf-8")
        next_state_paragraphs = []
        for paragraph in plan.split("\n\n"):
            normalized = " ".join(paragraph.split())
            lowered = normalized.lower()
            has_next_state_change = (
                "next state change" in lowered
                or "next planned state change" in lowered
            )
            if has_next_state_change and (
                "protected release" in lowered
                or "protected tag/publication evidence" in lowered
            ):
                next_state_paragraphs.append(lowered)

        self.assertGreaterEqual(len(next_state_paragraphs), 2)
        for paragraph in next_state_paragraphs:
            with self.subTest(paragraph=paragraph):
                self.assertIn("full validator is green", paragraph)

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name).resolve()
        self.project = root / "project"
        self.remote = root / "remote.git"
        self.outside_docs = root / "outside-docs"
        self.outside_docs.mkdir()
        self.outside_plan = root / "outside-plan.md"
        self.fake_bin = root / "fake-bin"
        self.real_git = shutil.which("git")
        if self.real_git is None:
            raise unittest.SkipTest("git is required for roadmap-state tests")
        (self.project / "scripts").mkdir(parents=True)
        (self.project / "docs/ai").mkdir(parents=True)
        (self.project / "docs/ai/escaped-plan.md").symlink_to("../../../outside-plan.md")
        (self.project / "docs/ai/in-repo-plan-link.md").symlink_to("MASTER_PLAN.md")
        (self.project / "linked-docs").symlink_to("../outside-docs", target_is_directory=True)
        self.fake_bin.mkdir()
        shutil.copy2(VERIFY, self.project / "scripts/verify-roadmap-state.sh")
        shutil.copy2(ROOT / "scripts/verify-github-remote.sh", self.project / "scripts/verify-github-remote.sh")
        shim = self.fake_bin / "git"
        shim.write_text(
            """#!/bin/sh
set -eu
real_git=${ROADMAP_TEST_REAL_GIT:?}
saw_remote=0
saw_get_url=0
saw_push=0
for arg in "$@"; do
	[ "$arg" = remote ] && saw_remote=1
	[ "$arg" = get-url ] && saw_get_url=1
	[ "$arg" = --push ] && saw_push=1
done
if [ "$saw_remote" -eq 1 ] && [ "$saw_get_url" -eq 1 ]; then
	if [ "$saw_push" -eq 1 ] && [ -n "${ROADMAP_TEST_EFFECTIVE_PUSH_URL:-}" ]; then
		printf '%s\\n' "$ROADMAP_TEST_EFFECTIVE_PUSH_URL"
		exit 0
	fi
	if [ "$saw_push" -eq 0 ] && [ -n "${ROADMAP_TEST_EFFECTIVE_FETCH_URL:-}" ]; then
		printf '%s\\n' "$ROADMAP_TEST_EFFECTIVE_FETCH_URL"
		exit 0
	fi
fi
exec "$real_git" "$@"
""",
            encoding="utf-8",
        )
        shim.chmod(0o755)

        (self.project / "README.md").write_text("roadmap fixture\n", encoding="utf-8")
        self.git("init", "-b", "main")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "user.name", "Roadmap State Test")
        self.git(
            "add",
            "README.md",
            "linked-docs",
            "docs/ai/escaped-plan.md",
            "docs/ai/in-repo-plan-link.md",
            "scripts/verify-roadmap-state.sh",
            "scripts/verify-github-remote.sh",
        )
        self.git("commit", "-m", "prepare roadmap fixture")
        baseline = self.git("rev-parse", "HEAD")
        fixture_plan = f"# Fixture plan\n\n- Review/audit baseline: `{baseline}`, fixture main\n"
        self.outside_plan.write_text(fixture_plan, encoding="utf-8")
        (self.outside_docs / "MASTER_PLAN.md").write_text(fixture_plan, encoding="utf-8")
        (self.project / "docs/ai/MASTER_PLAN.md").write_text(
            fixture_plan,
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

    def run_verify(
        self,
        mock_fetch_url: bool = True,
        mock_push_url: bool = True,
        plan_path: str = "docs/ai/MASTER_PLAN.md",
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["PATH"] = f"{self.fake_bin}{os.pathsep}{env['PATH']}"
        env["ROADMAP_TEST_REAL_GIT"] = self.real_git or "git"
        if mock_fetch_url:
            env["ROADMAP_TEST_EFFECTIVE_FETCH_URL"] = CANONICAL_URL
        else:
            env.pop("ROADMAP_TEST_EFFECTIVE_FETCH_URL", None)
        if mock_push_url:
            env["ROADMAP_TEST_EFFECTIVE_PUSH_URL"] = CANONICAL_URL
        else:
            env.pop("ROADMAP_TEST_EFFECTIVE_PUSH_URL", None)
        return subprocess.run(
            ["sh", str(self.project / "scripts/verify-roadmap-state.sh"), "origin", plan_path],
            cwd=self.project,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            env=env,
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

    def test_rejects_leading_parent_path_components(self) -> None:
        for plan_path in ("../outside-plan.md", "..//outside-plan.md", "docs/../outside-plan.md"):
            with self.subTest(plan_path=plan_path):
                result = self.run_verify(plan_path=plan_path)

                self.assertNotEqual(result.returncode, 0)
                self.assertIn("repository-relative file within the repository", result.stderr)
                self.assertIn("ROADMAP_STATE=BLOCKED", result.stderr)
                self.assertNotIn("ROADMAP_STATE=READY", result.stdout + result.stderr)

    def test_rejects_final_file_symlink_escape(self) -> None:
        result = self.run_verify(plan_path="docs/ai/escaped-plan.md")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("repository-relative file within the repository", result.stderr)
        self.assertIn("ROADMAP_STATE=BLOCKED", result.stderr)
        self.assertNotIn("ROADMAP_STATE=READY", result.stdout + result.stderr)

    def test_rejects_symlinked_parent_directory_escape(self) -> None:
        result = self.run_verify(plan_path="linked-docs/MASTER_PLAN.md")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("repository-relative file within the repository", result.stderr)
        self.assertIn("ROADMAP_STATE=BLOCKED", result.stderr)
        self.assertNotIn("ROADMAP_STATE=READY", result.stdout + result.stderr)

    def test_accepts_symlink_resolving_within_repository(self) -> None:
        result = self.run_verify(plan_path="docs/ai/in-repo-plan-link.md")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("ROADMAP_STATE=READY", result.stdout)
        self.assertIn("Audit relation: plan-only-head-parent", result.stdout)

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
        secret_url = "https://dummy-user:dummy-token@example.invalid/project.git"
        self.git("remote", "set-url", "origin", secret_url)

        result = self.run_verify(mock_fetch_url=False, mock_push_url=False)
        output = result.stdout + result.stderr

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unverified effective fetch URL", result.stderr)
        self.assertNotIn("dummy-user", output)
        self.assertNotIn("dummy-token", output)
        self.assertIn("ROADMAP_STATE=BLOCKED", result.stderr)

    def test_blocks_insteadof_redirect_before_tracking_ref_changes(self) -> None:
        original_tracking = self.git("rev-parse", "refs/remotes/origin/main")
        rogue = Path(self.temp.name) / "rogue.git"
        subprocess.run(["git", "init", "--bare", str(rogue)], check=True, capture_output=True, text=True)
        clone = Path(self.temp.name) / "rogue-clone"
        subprocess.run(["git", "clone", "--branch", "main", str(self.remote), str(clone)], check=True, capture_output=True, text=True)
        self.git_at(clone, "config", "user.email", "rogue@example.invalid")
        self.git_at(clone, "config", "user.name", "Rogue Mirror")
        (clone / "README.md").write_text("unapproved source\\n", encoding="utf-8")
        self.git_at(clone, "add", "README.md")
        self.git_at(clone, "commit", "-m", "rogue main update")
        self.git_at(clone, "remote", "set-url", "origin", str(rogue))
        self.git_at(clone, "push", "origin", "main")
        self.git("config", "--unset-all", f"url.{self.remote}.insteadOf")
        self.git("config", f"url.{rogue}.insteadOf", CANONICAL_URL)

        result = self.run_verify(mock_fetch_url=False, mock_push_url=False)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unverified effective fetch URL", result.stderr)
        self.assertIn("ROADMAP_STATE=BLOCKED", result.stderr)
        self.assertEqual(self.git("rev-parse", "refs/remotes/origin/main"), original_tracking)

    def test_blocks_pushinsteadof_redirect(self) -> None:
        rogue = Path(self.temp.name) / "rogue-push.git"
        self.git("config", f"url.{rogue}.pushInsteadOf", CANONICAL_URL)

        result = self.run_verify(mock_fetch_url=True, mock_push_url=False)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unverified effective push URL", result.stderr)
        self.assertIn("ROADMAP_STATE=BLOCKED", result.stderr)

    def test_rejects_push_url_without_echoing_credentials(self) -> None:
        secret_url = "https://dummy-user:dummy-token@example.invalid/project.git"
        self.git("remote", "set-url", "--push", "origin", secret_url)

        result = self.run_verify(mock_fetch_url=True, mock_push_url=False)
        output = result.stdout + result.stderr

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unverified effective push URL", result.stderr)
        self.assertNotIn("dummy-user", output)
        self.assertNotIn("dummy-token", output)
        self.assertIn("ROADMAP_STATE=BLOCKED", result.stderr)


if __name__ == "__main__":
    unittest.main()
