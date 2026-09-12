#!/usr/bin/env python3
"""Behavior checks for the read-only release preflight script."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PREFLIGHT = ROOT / "scripts/release-preflight.sh"


class ReleasePreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / "project"
        self.remote = self.root / "remote.git"
        (self.project / "xray-mitm").mkdir(parents=True)
        (self.project / "scripts").mkdir()
        (self.project / "xray-mitm/Makefile").write_text(
            "PKG_VERSION:=0.4.4\nPKG_RELEASE:=1\n", encoding="utf-8"
        )
        (self.project / "CHANGELOG.md").write_text(
            "# Changelog\n\n"
            "## [Unreleased]\n\n"
            "## [0.4.4] - 2026-09-13\n\n"
            "### Changed\n\n"
            "- Prepare the release.\n",
            encoding="utf-8",
        )
        (self.project / "scripts/release-notes.sh").write_text(
            "#!/bin/sh\n"
            "set -eu\n"
            "project_dir=\"$1\"\n"
            "tag=\"$2\"\n"
            "version=\"${tag#v}\"\n"
            "grep -Fq \"## [$version] - \" \"$project_dir/CHANGELOG.md\"\n"
            "printf '%s\\n' 'release notes'\n",
            encoding="utf-8",
        )
        self.validator = self.root / "validate.sh"
        self.validator.write_text(
            "#!/bin/sh\nprintf '%s\\n' 'fake validation passed'\n", encoding="utf-8"
        )

        self.git("init", "-b", "main")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "user.name", "Release Test")
        self.git("add", "CHANGELOG.md", "xray-mitm/Makefile", "scripts/release-notes.sh")
        self.git("commit", "-m", "prepare release test")
        subprocess.run(
            ["git", "clone", "--bare", str(self.project), str(self.remote)],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.git("remote", "add", "github", "https://github.com/duuuude/xray-mitm-openwrt.git")
        self.git(
            "config",
            f"url.{self.remote}.insteadOf",
            "https://github.com/duuuude/xray-mitm-openwrt.git",
        )

    def git(self, *args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(self.project), *args],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return result.stdout.strip()

    def git_remote(self, *args: str) -> str:
        result = subprocess.run(
            ["git", "--git-dir", str(self.remote), *args],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return result.stdout.strip()

    def sync_remote(self) -> None:
        self.git("push", "github", "HEAD:refs/heads/main")

    def run_preflight(self) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["RELEASE_PREFLIGHT_VALIDATE_CMD"] = str(self.validator)
        return subprocess.run(
            ["sh", str(PREFLIGHT), str(self.project)],
            cwd=self.project,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            check=False,
        )

    def commit_and_sync(self, message: str) -> None:
        self.git("add", "CHANGELOG.md", "xray-mitm/Makefile")
        self.git("commit", "-m", message)
        self.sync_remote()

    def test_success_checks_main_remote_and_validation(self) -> None:
        result = self.run_preflight()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("fake validation passed", result.stdout)
        self.assertIn("Release preflight passed.", result.stdout)
        self.assertIn("Ready to sign: v0.4.4", result.stdout)

    def test_requires_main_branch(self) -> None:
        self.git("switch", "-c", "feature/release")

        result = self.run_preflight()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must run on main", result.stderr)

    def test_requires_clean_worktree(self) -> None:
        (self.project / "untracked.txt").write_text("dirty\n", encoding="utf-8")

        result = self.run_preflight()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("worktree is not clean", result.stderr)

    def test_requires_verified_github_remote(self) -> None:
        self.git("remote", "set-url", "github", "https://example.invalid/project.git")

        result = self.run_preflight()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("verified duuuude/xray-mitm-openwrt GitHub repository", result.stderr)

    def test_requires_synchronized_main(self) -> None:
        (self.project / "CHANGELOG.md").write_text(
            (self.project / "CHANGELOG.md").read_text(encoding="utf-8")
            + "\n",
            encoding="utf-8",
        )
        self.git("add", "CHANGELOG.md")
        self.git("commit", "-m", "make local main diverge")

        result = self.run_preflight()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not synchronized", result.stderr)

    def test_rejects_local_tag(self) -> None:
        self.git("tag", "v0.4.4")

        result = self.run_preflight()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("already exists locally", result.stderr)

    def test_rejects_remote_tag(self) -> None:
        self.git_remote("update-ref", "refs/tags/v0.4.4", self.git("rev-parse", "HEAD"))

        result = self.run_preflight()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("already exists on", result.stderr)

    def test_requires_release_one(self) -> None:
        (self.project / "xray-mitm/Makefile").write_text(
            "PKG_VERSION:=0.4.4\nPKG_RELEASE:=2\n", encoding="utf-8"
        )
        self.commit_and_sync("set non-release package revision")

        result = self.run_preflight()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("PKG_RELEASE must be 1", result.stderr)

    def test_requires_dated_release_section(self) -> None:
        changelog = self.project / "CHANGELOG.md"
        changelog.write_text(
            changelog.read_text(encoding="utf-8").replace(
                "## [0.4.4] - 2026-09-13", "## [0.4.4]"
            ),
            encoding="utf-8",
        )
        self.commit_and_sync("remove release date")

        result = self.run_preflight()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no dated section", result.stderr)

    def test_rejects_entries_left_under_unreleased(self) -> None:
        changelog = self.project / "CHANGELOG.md"
        changelog.write_text(
            changelog.read_text(encoding="utf-8").replace(
                "## [Unreleased]\n", "## [Unreleased]\n\n- Still unreleased.\n"
            ),
            encoding="utf-8",
        )
        self.commit_and_sync("leave unreleased entry")

        result = self.run_preflight()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("still contains entries under Unreleased", result.stderr)

    def test_reports_full_validation_failure(self) -> None:
        self.validator.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")

        result = self.run_preflight()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Full release validation failed", result.stderr)

    def test_does_not_contain_tag_or_push_commands(self) -> None:
        source = PREFLIGHT.read_text(encoding="utf-8")

        self.assertNotIn("git_at tag", source)
        self.assertNotIn("git_at push", source)


if __name__ == "__main__":
    unittest.main()
