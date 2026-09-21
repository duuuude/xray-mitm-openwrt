#!/usr/bin/env python3
"""Static trust-boundary and release-version tests for the signed APK feed."""

from __future__ import annotations

import re
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "install.sh"
WORKFLOW = ROOT / ".github/workflows/publish-feed.yml"
CANDIDATE_WORKFLOW = ROOT / ".github/workflows/sign-candidate.yml"
PUBLIC_KEY = ROOT / "keys/xray-mitm-feed-v1.pem"
VERSION_CHECK = ROOT / "scripts/check-release-version.sh"
RELEASE_NOTES = ROOT / "scripts/release-notes.sh"
EXPECTED_KEY_SHA256 = "3e0dc07ffef69d1512500b6add486381d8c261a8ec3fcce54fa403b35320df8a"
EXPECTED_INSTALLER_SHA256 = "1dd25456a33ebfe21e780519a3a901ae09e54668cbde4493a96cfb3185ef4b63"
PACKAGE_VERSION = next(
    line.split(":=", 1)[1].strip()
    for line in (ROOT / "xray-mitm/Makefile").read_text(encoding="utf-8").splitlines()
    if line.startswith("PKG_VERSION:=")
)


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
        self.assertIn("actions: read", text)
        self.assertEqual(text.count("secrets.XRAY_MITM_APK_PRIVATE_KEY"), 2)
        self.assertIn("actions/download-artifact@", text)
        self.assertIn("run-id:", text)
        self.assertIn("scripts/verify-promotion-artifact.sh", text)
        self.assertIn("scripts/sign-apk-index.sh", text)
        self.assertIn("ghcr.io/openwrt/sdk:", text)
        self.assertNotIn("openwrt/gh-action-sdk@", text)
        self.assertIn("actions/deploy-pages@", text)
        self.assertNotIn("--allow-untrusted", text)

    def test_publish_workflow_promotes_exact_main_build_without_rebuilding(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("actions/workflows/build.yml/runs", text)
        self.assertIn("head_sha=${GITHUB_SHA}", text)
        self.assertIn("status=completed", text)
        self.assertIn('select(.conclusion == "success")', text)
        self.assertIn("BUILD_RUN_ID", text)
        self.assertIn("BUILD_PACKAGE_SHA256SUMS", text)
        self.assertIn("SOURCE_COMMIT", text)
        self.assertIn("RELEASE_COMMIT", text)
        self.assertIn("Sign the exact package index without rebuilding packages", text)
        self.assertNotIn("Build packages and signed OpenWrt index", text)

    def test_candidate_workflow_is_manual_exact_head_and_nonpublishing(self) -> None:
        text = CANDIDATE_WORKFLOW.read_text(encoding="utf-8")

        self.assertRegex(text, r"(?m)^\s+workflow_dispatch:\s*$")
        self.assertNotRegex(text, r"(?m)^\s+push:\s*$")
        self.assertNotRegex(text, r"(?m)^\s+pull_request:\s*$")
        self.assertNotRegex(text, r"(?m)^\s+tags:\s*$")
        self.assertIn("contents: read", text)
        self.assertIn("pull-requests: read", text)
        self.assertIn("environment: signed-feed", text)
        self.assertEqual(text.count("secrets.XRAY_MITM_APK_PRIVATE_KEY"), 2)
        self.assertIn("pr_number", text)
        self.assertIn("candidate_sha", text)
        self.assertIn('test "$GITHUB_REF" = "refs/heads/main"', text)
        self.assertIn(
            'test "$(jq -r \'.head.sha\' <<<"$pr_json")" = "$CANDIDATE_SHA"',
            text,
        )
        self.assertIn(
            'test "$(jq -r \'.head.repo.full_name\' <<<"$pr_json")" = "$GITHUB_REPOSITORY"',
            text,
        )
        self.assertIn('BASE_SHA: ${{ steps.verify_pr.outputs.base_sha }}', text)
        self.assertIn('git diff --check "$BASE_SHA" "$CANDIDATE_SHA"', text)
        self.assertNotRegex(text, r"(?m)^\s+git diff --check\s*$")
        self.assertIn("test \"$(git rev-parse HEAD)\" = \"$CANDIDATE_SHA\"", text)
        self.assertIn("git merge-base --is-ancestor", text)
        self.assertIn('INDEX: "1"', text)
        self.assertIn("packages.adb", text)
        self.assertIn("SOURCE_COMMIT", text)
        self.assertIn("BASE_COMMIT", text)
        self.assertIn("PUBLIC_KEY_SHA256", text)
        self.assertIn("actions/upload-artifact@", text)
        self.assertIn("retention-days: 7", text)
        self.assertNotIn("gh release", text)
        self.assertNotIn("upload-pages-artifact@", text)
        self.assertNotIn("deploy-pages@", text)
        self.assertNotIn("--allow-untrusted", text)

        protected_job = text.split("  build-and-sign:\n", 1)[1]
        recheck_start = protected_job.index(
            "      - name: Revalidate PR identity after protected gate"
        )
        secret_start = protected_job.index(
            "secrets.XRAY_MITM_APK_PRIVATE_KEY", recheck_start
        )
        recheck = protected_job[recheck_start:secret_start]
        self.assertIn("gh api", recheck)
        for field in (".state", ".base.ref", ".head.sha", ".head.repo.full_name"):
            self.assertIn(field, recheck)
        self.assertIn('test "$GITHUB_REF" = "refs/heads/main"', recheck)

    def test_public_bootstrap_is_published_and_checksum_pinned(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        installer_digest = subprocess.check_output(
            ["sha256sum", str(INSTALLER)], text=True
        ).split()[0]

        self.assertEqual(installer_digest, EXPECTED_INSTALLER_SHA256)
        self.assertIn(f"'{EXPECTED_INSTALLER_SHA256}'", workflow)
        self.assertIn("cp install.sh site/install.sh", workflow)
        self.assertIn("site/INSTALLER_SHA256", workflow)
        self.assertIn('"signed-site/install.sh"', workflow)
        self.assertIn('"signed-site/INSTALLER_SHA256"', workflow)

        for readme in (ROOT / "README.md", ROOT / "README.fa.md"):
            text = readme.read_text(encoding="utf-8")
            self.assertNotIn("raw.githubusercontent.com", text)
            self.assertIn(
                "https://duuuude.github.io/xray-mitm-openwrt/install.sh", text
            )
            self.assertEqual(text.count(EXPECTED_INSTALLER_SHA256), 4)

    def test_release_checksums_use_final_github_asset_names(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")

        self.assertIn('release_name="${apk_name//\\~/.}"', workflow)
        self.assertIn('cd "$release_dir"', workflow)
        self.assertIn("sha256sum ./*.apk packages.adb install.sh", workflow)
        self.assertIn('"$release_dir"/*', workflow)
        self.assertNotIn('"$feed_dir/SHA256SUMS"', workflow)

    def test_installer_uses_native_signed_repository_only(self) -> None:
        text = INSTALLER.read_text(encoding="utf-8")

        self.assertIn("/etc/apk/keys", text)
        self.assertIn("/etc/apk/repositories.d", text)
        self.assertIn("/etc/opkg/keys", text)
        self.assertIn("/etc/opkg/customfeeds.conf", text)
        self.assertIn("/etc/opkg.conf", text)
        self.assertIn("detect_platform()", text)
        self.assertIn("check_platform_support()", text)
        self.assertIn("supported_opkg_release()", text)
        self.assertIn("check_signature", text)
        self.assertIn("validate_https_url()", text)
        self.assertIn("usign -F -p", text)
        self.assertIn("OPKG_KEY_FINGERPRINT", text)
        self.assertIn('"${#OPKG_KEY_FINGERPRINT}" -eq 16', text)
        self.assertIn('"$APK_BIN" add xray-mitm luci-app-xray-mitm', text)
        self.assertIn('"$APK_BIN" upgrade xray-mitm luci-app-xray-mitm', text)
        self.assertIn('"$OPKG_BIN" install xray-mitm luci-app-xray-mitm', text)
        self.assertIn('"$OPKG_BIN" upgrade xray-mitm luci-app-xray-mitm', text)
        self.assertIn("OPKG_FEED_NAME='xray_mitm'", text)
        self.assertIn('src/gz "', text)
        self.assertIn("BACKUP_RETENTION=3", text)
        self.assertNotIn("allow-untrusted", text.replace(
            "--allow-untrusted was not used", ""
        ))

    def test_luci_fallback_version_matches_package_version(self) -> None:
        makefile = (ROOT / "xray-mitm/Makefile").read_text(encoding="utf-8")
        overview = (ROOT / "luci-app-xray-mitm/htdocs/luci-static/resources/view/xray-mitm/overview.js").read_text(encoding="utf-8")
        version = re.search(r"^PKG_VERSION:=([^\r\n]+)$", makefile, re.MULTILINE)

        self.assertIsNotNone(version)
        self.assertIn(
            f"var PROJECT_VERSION = '{version.group(1)}';",
            overview,
        )

    def test_release_tag_must_match_package_version(self) -> None:
        # Development builds may use a non-r1 package release so that a
        # changed package can be installed over the published baseline. Test
        # the tag checker with the release-state contract independently.
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Path(temporary)
            (fixture / "xray-mitm").mkdir()
            (fixture / "scripts").mkdir()
            makefile = (ROOT / "xray-mitm/Makefile").read_text(encoding="utf-8")
            makefile = re.sub(
                r"^PKG_RELEASE:=[^\r\n]+$",
                "PKG_RELEASE:=1",
                makefile,
                count=1,
                flags=re.MULTILINE,
            )
            (fixture / "xray-mitm/Makefile").write_text(makefile, encoding="utf-8")
            (fixture / "CHANGELOG.md").write_text(
                (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            release_notes = fixture / "scripts/release-notes.sh"
            release_notes.write_text(
                RELEASE_NOTES.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            release_notes.chmod(0o755)

            good = subprocess.run(
                ["sh", str(VERSION_CHECK), str(fixture), f"v{PACKAGE_VERSION}"],
                text=True,
                capture_output=True,
                check=False,
            )
            bad = subprocess.run(
                [
                    "sh",
                    str(VERSION_CHECK),
                    str(fixture),
                    f"v{PACKAGE_VERSION}-invalid",
                ],
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(good.returncode, 0, good.stdout + good.stderr)
        self.assertNotEqual(bad.returncode, 0)
        self.assertIn("does not match", bad.stderr)

    def test_release_notes_come_from_matching_changelog_section(self) -> None:
        result = subprocess.run(
            ["sh", str(RELEASE_NOTES), str(ROOT), "v0.2.2"],
            text=True,
            capture_output=True,
            check=False,
        )
        missing = subprocess.run(
            ["sh", str(RELEASE_NOTES), str(ROOT), "v9.9.9"],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("one-command installer", result.stdout)
        self.assertNotIn("0.2.1", result.stdout)
        self.assertNotEqual(missing.returncode, 0)
        self.assertIn("no notes", missing.stderr)

        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("scripts/release-notes.sh", workflow)
        self.assertIn("--notes-file signed-site/RELEASE_NOTES.md", workflow)

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
