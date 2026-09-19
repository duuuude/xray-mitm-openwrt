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
        self.assertNotIn("24.10.8", workflow)
        self.assertNotIn(".ipk", workflow)

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


if __name__ == "__main__":
    unittest.main()
