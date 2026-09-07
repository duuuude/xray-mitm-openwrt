#!/usr/bin/env python3
"""Behavior checks for the release installer without network or router access."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "install.sh"
CORE_ASSET = "xray-mitm-0.1.0-r4.apk"
LUCI_ASSET = "luci-app-xray-mitm-26.249.69617~5f96cdb.apk"


class InstallerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin_dir = self.root / "bin"
        self.fixtures = self.root / "fixtures"
        self.bin_dir.mkdir()
        self.fixtures.mkdir()
        self.apk_log = self.root / "apk.log"
        self.release_file = self.root / "openwrt_release"
        self.release_file.write_text("DISTRIB_RELEASE='25.12.5'\n", encoding="utf-8")

        (self.fixtures / CORE_ASSET).write_bytes(b"core package\n")
        (self.fixtures / LUCI_ASSET).write_bytes(b"luci package\n")
        self.write_manifest()

        self.write_fake(
            "id",
            """
            import os
            print(os.environ.get("FAKE_UID", "0"))
            """,
        )
        self.write_fake(
            "uclient-fetch",
            """
            import os
            import shutil
            import sys
            from pathlib import Path

            destination = Path(sys.argv[sys.argv.index("-O") + 1])
            asset = sys.argv[-1].rsplit("/", 1)[-1]
            shutil.copyfile(Path(os.environ["XRAY_MITM_FIXTURES"]) / asset, destination)
            """,
        )
        self.write_fake(
            "sha256sum",
            """
            import hashlib
            import sys
            from pathlib import Path

            if len(sys.argv) != 3 or sys.argv[1] != "-c":
                raise SystemExit(2)
            ok = True
            for line in Path(sys.argv[2]).read_text(encoding="utf-8").splitlines():
                expected, name = line.split(None, 1)
                actual = hashlib.sha256(Path(name).read_bytes()).hexdigest()
                if actual == expected:
                    print(f"{name}: OK")
                else:
                    print(f"{name}: FAILED", file=sys.stderr)
                    ok = False
            raise SystemExit(0 if ok else 1)
            """,
        )
        self.write_fake(
            "apk",
            """
            import json
            import os
            import sys
            from pathlib import Path

            with Path(os.environ["XRAY_MITM_APK_LOG"]).open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(sys.argv[1:]) + "\\n")
            """,
        )

    def write_fake(self, name: str, body: str) -> None:
        path = self.bin_dir / name
        path.write_text(
            "#!/usr/bin/env python3\n" + textwrap.dedent(body).lstrip(),
            encoding="utf-8",
        )
        path.chmod(0o755)

    def write_manifest(self, core_hash: str | None = None) -> None:
        entries = []
        for name in (LUCI_ASSET, CORE_ASSET):
            digest = hashlib.sha256((self.fixtures / name).read_bytes()).hexdigest()
            if name == CORE_ASSET and core_hash is not None:
                digest = core_hash
            entries.append(f"{digest}  {name}\n")
        (self.fixtures / "SHA256SUMS").write_text("".join(entries), encoding="utf-8")

    def run_installer(self, *, fake_uid: str = "0") -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.update(
            {
                "FAKE_UID": fake_uid,
                "PATH": f"{self.bin_dir}:{env['PATH']}",
                "XRAY_MITM_APK_LOG": str(self.apk_log),
                "XRAY_MITM_BASE_URL": "https://fixtures.invalid/release",
                "XRAY_MITM_FIXTURES": str(self.fixtures),
                "XRAY_MITM_OPENWRT_RELEASE_FILE": str(self.release_file),
            }
        )
        return subprocess.run(
            ["sh", str(INSTALLER)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            check=False,
        )

    def apk_calls(self) -> list[list[str]]:
        if not self.apk_log.exists():
            return []
        return [json.loads(line) for line in self.apk_log.read_text().splitlines()]

    def test_downloads_verifies_and_installs_both_packages(self) -> None:
        result = self.run_installer()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Installation complete.", result.stdout)
        self.assertEqual(
            self.apk_calls(),
            [
                ["update"],
                ["add", "--allow-untrusted", f"./{CORE_ASSET}", f"./{LUCI_ASSET}"],
            ],
        )

    def test_checksum_failure_stops_before_apk_changes(self) -> None:
        self.write_manifest(core_hash="0" * 64)

        result = self.run_installer()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FAILED", result.stderr)
        self.assertEqual(self.apk_calls(), [])

    def test_package_list_selects_names_for_a_future_release(self) -> None:
        core = "xray-mitm-0.2.0-r1.apk"
        luci = "luci-app-xray-mitm-0.2.0-r1.apk"
        (self.fixtures / core).write_bytes(b"future core package\n")
        (self.fixtures / luci).write_bytes(b"future luci package\n")
        (self.fixtures / "PACKAGES").write_text(f"{luci}\n{core}\n", encoding="utf-8")
        entries = []
        for name in (luci, core):
            digest = hashlib.sha256((self.fixtures / name).read_bytes()).hexdigest()
            entries.append(f"{digest}  {name}\n")
        (self.fixtures / "SHA256SUMS").write_text("".join(entries), encoding="utf-8")

        result = self.run_installer()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            self.apk_calls(),
            [
                ["update"],
                ["add", "--allow-untrusted", f"./{core}", f"./{luci}"],
            ],
        )

    def test_incomplete_package_list_stops_before_download_or_install(self) -> None:
        (self.fixtures / "PACKAGES").write_text(f"{LUCI_ASSET}\n", encoding="utf-8")

        result = self.run_installer()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not identify exactly one core APK", result.stderr)
        self.assertEqual(self.apk_calls(), [])

    def test_requires_root(self) -> None:
        result = self.run_installer(fake_uid="1000")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Run this installer as root", result.stderr)
        self.assertEqual(self.apk_calls(), [])

    def test_rejects_an_older_openwrt_release(self) -> None:
        self.release_file.write_text("DISTRIB_RELEASE='25.12.4'\n", encoding="utf-8")

        result = self.run_installer()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("25.12.5 or later is required", result.stderr)
        self.assertEqual(self.apk_calls(), [])


if __name__ == "__main__":
    unittest.main()
