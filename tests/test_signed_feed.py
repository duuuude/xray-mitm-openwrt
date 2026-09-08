#!/usr/bin/env python3
"""Static trust-boundary and release-version tests for the signed APK feed."""

from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "install.sh"
WORKFLOW = ROOT / ".github/workflows/publish-feed.yml"
PUBLIC_KEY = ROOT / "keys/xray-mitm-feed-v1.pem"
VERSION_CHECK = ROOT / "scripts/check-release-version.sh"
EXPECTED_KEY_SHA256 = "3e0dc07ffef69d1512500b6add486381d8c261a8ec3fcce54fa403b35320df8a"


class SignedFeedTests(unittest.TestCase):
    def test_committed_key_is_public_and_matches_installer_pin(self) -> None:
        payload = PUBLIC_KEY.read_text(encoding="ascii")
        installer = INSTALLER.read_text(encoding="utf-8")

        self.assertIn("-----BEGIN PUBLIC KEY-----", payload)
        self.assertNotIn("PRIVATE KEY", payload)
        digest = subprocess.check_output(
            ["sha256sum", str(PUBLIC_KEY)], text=True
        ).split()[0]
        self.assertEqual(digest, EXPECTED_KEY_SHA256)
        self.assertIn(EXPECTED_KEY_SHA256, installer)

    def test_workflow_is_tag_only_and_scopes_secret_to_protected_job(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")

        self.assertRegex(text, r"(?m)^\s+tags:\s*$")
        self.assertNotIn("pull_request:", text)
        self.assertNotIn("workflow_dispatch:", text)
        self.assertIn("environment: signed-feed", text)
        self.assertEqual(text.count("secrets.XRAY_MITM_APK_PRIVATE_KEY"), 2)
        self.assertIn('INDEX: "1"', text)
        self.assertIn("actions/deploy-pages@", text)
        self.assertNotIn("--allow-untrusted", text)

    def test_installer_uses_native_signed_repository_only(self) -> None:
        text = INSTALLER.read_text(encoding="utf-8")

        self.assertIn("/etc/apk/keys", text)
        self.assertIn("/etc/apk/repositories.d", text)
        self.assertRegex(text, r"apk add xray-mitm luci-app-xray-mitm")
        self.assertNotIn("apk upgrade", text)
        self.assertNotIn("allow-untrusted", text.replace(
            "--allow-untrusted was not used", ""
        ))

    def test_release_tag_must_match_package_version(self) -> None:
        good = subprocess.run(
            ["sh", str(VERSION_CHECK), str(ROOT), "v0.2.0"],
            text=True,
            capture_output=True,
            check=False,
        )
        bad = subprocess.run(
            ["sh", str(VERSION_CHECK), str(ROOT), "v0.2.1"],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(good.returncode, 0, good.stdout + good.stderr)
        self.assertNotEqual(bad.returncode, 0)
        self.assertIn("does not match", bad.stderr)

    def test_all_workflow_actions_are_pinned_to_commits(self) -> None:
        for workflow in (ROOT / ".github/workflows").glob("*.yml"):
            text = workflow.read_text(encoding="utf-8")
            actions = re.findall(
                r"(?m)^\s*(?:-\s*)?uses:\s*([^ #]+)", text
            )
            self.assertTrue(actions, workflow)
            for action in actions:
                self.assertRegex(action, r"^[^@\s]+@[0-9a-f]{40}$")


if __name__ == "__main__":
    unittest.main()
