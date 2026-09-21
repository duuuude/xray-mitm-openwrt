#!/usr/bin/env python3
"""Regression tests for exact APK promotion-artifact verification."""

from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERIFY = ROOT / "scripts/verify-promotion-artifact.sh"
SOURCE = "0123456789abcdef0123456789abcdef01234567"
RELEASE = "25.12.5"
ARCH = "aarch64_generic"


class PromotionArtifactTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.artifact = Path(self.temp.name) / "artifact"
        self.artifact.mkdir()
        (self.artifact / "xray-mitm-0.4.4.apk").write_bytes(b"core")
        (self.artifact / "luci-app-xray-mitm-26.258.50325.apk").write_bytes(b"luci")
        (self.artifact / "packages.adb").write_bytes(b"unsigned index")
        (self.artifact / "SOURCE_COMMIT").write_text(SOURCE + "\n", encoding="utf-8")
        (self.artifact / "OPENWRT_RELEASE").write_text(RELEASE + "\n", encoding="utf-8")
        (self.artifact / "SDK_ARCH").write_text(ARCH + "\n", encoding="utf-8")
        (self.artifact / "PACKAGE_FORMAT").write_text("apk\n", encoding="utf-8")
        (self.artifact / "ARTIFACT_PURPOSE").write_text(
            "promotable unsigned APK bundle\n", encoding="utf-8"
        )
        (self.artifact / "PACKAGES").write_text(
            "luci-app-xray-mitm-26.258.50325.apk\n"
            "xray-mitm-0.4.4.apk\n",
            encoding="utf-8",
        )
        self.write_checksums()

    def write_checksums(self) -> None:
        files = [
            self.artifact / "luci-app-xray-mitm-26.258.50325.apk",
            self.artifact / "xray-mitm-0.4.4.apk",
        ]
        package_lines = []
        for path in files:
            package_lines.append(
                f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}"
            )
        (self.artifact / "PACKAGE_SHA256SUMS").write_text(
            "\n".join(package_lines) + "\n", encoding="utf-8"
        )
        all_files = files + [self.artifact / "packages.adb"]
        (self.artifact / "SHA256SUMS").write_text(
            "\n".join(
                f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}"
                for path in all_files
            )
            + "\n",
            encoding="utf-8",
        )

    def run_verify(self, source: str = SOURCE) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["sh", str(VERIFY), str(self.artifact), source, RELEASE, ARCH],
            text=True,
            capture_output=True,
            check=False,
            env={**os.environ, "LC_ALL": "C"},
        )

    def test_accepts_exact_complete_artifact(self) -> None:
        result = self.run_verify()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Promotion artifact verified", result.stdout)

    def test_rejects_wrong_source_commit(self) -> None:
        result = self.run_verify("fedcba9876543210fedcba9876543210fedcba98")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("source commit", result.stderr)

    def test_rejects_changed_package_bytes(self) -> None:
        (self.artifact / "xray-mitm-0.4.4.apk").write_bytes(b"changed")
        result = self.run_verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("checksum did NOT match", result.stderr)

    def test_rejects_extra_apk(self) -> None:
        (self.artifact / "unexpected-1.apk").write_bytes(b"extra")
        result = self.run_verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("exactly two APKs", result.stderr)

    def test_rejects_incomplete_checksum_manifest(self) -> None:
        lines = (self.artifact / "PACKAGE_SHA256SUMS").read_text(encoding="utf-8").splitlines()
        (self.artifact / "PACKAGE_SHA256SUMS").write_text(
            lines[0] + "\n", encoding="utf-8"
        )
        result = self.run_verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("PACKAGE_SHA256SUMS", result.stderr)


if __name__ == "__main__":
    unittest.main()
