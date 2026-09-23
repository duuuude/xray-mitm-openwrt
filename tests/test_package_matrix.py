#!/usr/bin/env python3
"""Offline checks for the dual-family package build contract."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CORE_MAKEFILE = ROOT / "xray-mitm/Makefile"
LUCI_MAKEFILE = ROOT / "luci-app-xray-mitm/Makefile"
APK_WORKFLOW = ROOT / ".github/workflows/build.yml"
IPK_WORKFLOW = ROOT / ".github/workflows/build-24-10.yml"
PR_EVIDENCE_WORKFLOW = ROOT / ".github/workflows/pr-evidence.yml"


class PackageMatrixTests(unittest.TestCase):
    def test_makefiles_are_release_family_neutral(self) -> None:
        core = CORE_MAKEFILE.read_text(encoding="utf-8")
        luci = LUCI_MAKEFILE.read_text(encoding="utf-8")

        self.assertNotIn("@USE_APK", core)
        self.assertNotIn("@USE_APK", luci)
        self.assertIn("PKGARCH:=all", core)
        self.assertIn("LUCI_PKGARCH:=all", luci)
        for dependency in (
            "+xray-core",
            "+curl",
            "+openssl-util",
            "+uci",
            "+jsonfilter",
            "+coreutils-stat",
            "+v2ray-geoip",
            "+v2ray-geosite",
        ):
            self.assertIn(dependency, core)
        for dependency in ("+luci-base", "+xray-mitm", "+rpcd-mod-ucode", "+ucode-mod-fs"):
            self.assertIn(dependency, luci)

    def test_existing_apk_lane_remains_25_12_and_apk_only(self) -> None:
        workflow = APK_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn('name: Build OpenWrt APKs', workflow)
        self.assertIn("25.12.5", workflow)
        self.assertIn("aarch64_generic", workflow)
        self.assertIn("xray-mitm-*.apk", workflow)
        self.assertIn("luci-app-xray-mitm-*.apk", workflow)
        self.assertIn('INDEX: "1"', workflow)
        self.assertIn("packages.adb", workflow)
        self.assertIn("PACKAGE_SHA256SUMS", workflow)
        self.assertIn("ARTIFACT_PURPOSE", workflow)
        self.assertNotIn("24.10.8", workflow)
        self.assertNotIn(".ipk", workflow)
        self.assertNotIn("PRIVATE_KEY", workflow)
        self.assertEqual(
            workflow.count(
                "ref: ${{ github.event.pull_request.head.sha || github.sha }}"
            ),
            2,
        )
        self.assertIn('source_commit="$(git rev-parse HEAD)"', workflow)
        self.assertIn('printf \'%s\\n\' "$source_commit" > dist/SOURCE_COMMIT', workflow)
        self.assertNotIn('printf \'%s\\n\' "$GITHUB_SHA" > dist/SOURCE_COMMIT', workflow)

    def test_apk_lane_is_path_filtered_to_package_changes(self) -> None:
        workflow = APK_WORKFLOW.read_text(encoding="utf-8")

        self.assertRegex(workflow, r"(?ms)^  pull_request:\n    paths:\n")
        self.assertRegex(
            workflow,
            r"(?ms)^  push:\n    branches:\n(?:      - .+\n)+    paths:\n",
        )
        for path in (
            ".github/workflows/build.yml",
            "ci/**",
            "install.sh",
            "luci-app-xray-mitm/**",
            "scripts/**",
            "tests/**",
            "xray-mitm/**",
        ):
            self.assertIn(f'      - "{path}"', workflow)
        self.assertNotIn('      - "docs/**"', workflow)

    def test_24_10_lane_is_bounded_unsigned_ipk_build(self) -> None:
        workflow = IPK_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("name: Build OpenWrt 24.10 IPKs", workflow)
        self.assertIn("24.10.8", workflow)
        self.assertIn("aarch64_cortex-a53", workflow)
        self.assertIn("openwrt/gh-action-sdk@", workflow)
        self.assertIn("xray-mitm_*.ipk", workflow)
        self.assertIn("luci-app-xray-mitm_*.ipk", workflow)
        self.assertIn("PACKAGE_FORMAT", workflow)
        self.assertIn("SOURCE_COMMIT", workflow)
        self.assertIn("SHA256SUMS", workflow)
        self.assertIn("PACKAGES", workflow)
        self.assertEqual(
            workflow.count('      - "scripts/validate-release.sh"'),
            2,
        )
        self.assertEqual(
            workflow.count('      - "scripts/verify-github-remote.sh"'),
            2,
        )
        self.assertEqual(
            workflow.count(
                "ref: ${{ github.event.pull_request.head.sha || github.sha }}"
            ),
            2,
        )
        self.assertIn('CHECK_PR_ALLOW_MANUAL_GATES: "1"', workflow)
        self.assertIn("sh scripts/check-pr.sh", workflow)
        self.assertIn("pr-evidence-source-", workflow)
        self.assertIn("actions/download-artifact@", workflow)
        self.assertIn("scripts/pr-evidence.py attach-build", workflow)
        self.assertIn("pr-evidence-ipk-", workflow)

        for forbidden in (
            "KEY_BUILD",
            "PRIVATE_KEY",
            "packages.adb",
            "actions/deploy-pages",
            "--allow-untrusted",
        ):
            self.assertNotIn(forbidden, workflow)

        self.assertRegex(workflow, r"uses: actions/checkout@[0-9a-f]{40}")
        self.assertRegex(workflow, r"uses: openwrt/gh-action-sdk@[0-9a-f]{40}")
        self.assertRegex(workflow, r"uses: actions/upload-artifact@[0-9a-f]{40}")

    def test_24_10_path_filters_cover_evidence_helpers_and_tests(self) -> None:
        workflow = IPK_WORKFLOW.read_text(encoding="utf-8")
        trigger_blocks = {
            "pull_request": workflow.split("  pull_request:\n", 1)[1].split(
                "\n  push:\n", 1
            )[0],
            "push": workflow.split("  push:\n", 1)[1].split(
                "\n\npermissions:", 1
            )[0],
        }

        required_paths = (
            "scripts/check-pr.sh",
            "scripts/pr-evidence.py",
            "tests/test_check_pr.py",
            "tests/test_pr_evidence.py",
        )
        for trigger, block in trigger_blocks.items():
            with self.subTest(trigger=trigger):
                self.assertIn("    paths:\n", block)
                paths_section = block.split("    paths:\n", 1)[1]
                for path in required_paths:
                    self.assertIn(f'      - "{path}"', paths_section)

    def test_docs_evidence_workflow_is_lightweight_and_candidate_bound(self) -> None:
        workflow = PR_EVIDENCE_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("pull_request:", workflow)
        self.assertIn('      - "*.md"', workflow)
        self.assertIn('      - "**/*.md"', workflow)
        self.assertIn("github.event.pull_request.base.sha", workflow)
        self.assertIn("github.event.pull_request.head.sha", workflow)
        self.assertIn("PR_EVIDENCE_PATH:", workflow)
        self.assertIn("sh scripts/check-pr.sh", workflow)
        self.assertIn("retention-days: 30", workflow)
        self.assertNotIn("openwrt/gh-action-sdk", workflow)
        self.assertNotIn("actions/download-artifact", workflow)
        self.assertNotIn('      - "scripts/**"', workflow)
        self.assertNotIn('      - "tests/**"', workflow)
        self.assertNotIn('      - "xray-mitm/**"', workflow)

    def test_both_package_workflows_attach_verified_hashes_to_standard_evidence(self) -> None:
        for workflow_path, artifact_prefix in (
            (APK_WORKFLOW, "pr-evidence-apk-"),
            (IPK_WORKFLOW, "pr-evidence-ipk-"),
        ):
            with self.subTest(workflow=workflow_path.name):
                workflow = workflow_path.read_text(encoding="utf-8")
                self.assertIn("PR_EVIDENCE_PATH:", workflow)
                self.assertIn("sh scripts/check-pr.sh", workflow)
                self.assertIn("pr-evidence-source-", workflow)
                self.assertIn("actions/download-artifact@", workflow)
                self.assertIn("scripts/pr-evidence.py attach-build", workflow)
                self.assertIn('--source-sha "$CANDIDATE_SHA"', workflow)
                self.assertIn(artifact_prefix, workflow)
                self.assertIn("retention-days: 30", workflow)


if __name__ == "__main__":
    unittest.main()
