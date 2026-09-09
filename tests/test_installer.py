#!/usr/bin/env python3
"""Behavior checks for the signed-feed installer without network or router access."""

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
KEY_NAME = "xray-mitm-feed-v1.pem"
FEED_URL = "https://fixtures.invalid/feed/25.12/all/packages.adb"


class InstallerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin_dir = self.root / "bin"
        self.fixtures = self.root / "fixtures"
        self.keys_dir = self.root / "etc/apk/keys"
        self.repositories_dir = self.root / "etc/apk/repositories.d"
        self.keep_dir = self.root / "lib/upgrade/keep.d"
        self.backup_dir = self.root / "root"
        self.config_file = self.root / "etc/config/xray-mitm"
        self.state_dir = self.root / "etc/xray-mitm"
        self.world_file = self.root / "etc/apk/world"
        for directory in (
            self.bin_dir,
            self.fixtures,
            self.keys_dir,
            self.repositories_dir,
            self.keep_dir,
            self.backup_dir,
            self.config_file.parent,
            self.state_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

        self.apk_log = self.root / "apk.log"
        self.release_file = self.root / "openwrt_release"
        self.release_file.write_text("DISTRIB_RELEASE='25.12.5'\n", encoding="utf-8")
        self.world_file.write_text("base-files\n", encoding="utf-8")
        self.public_key = self.fixtures / KEY_NAME
        self.public_key.write_text(
            "-----BEGIN PUBLIC KEY-----\n"
            "test-only-public-key-material\n"
            "-----END PUBLIC KEY-----\n",
            encoding="utf-8",
        )
        self.public_key_sha256 = hashlib.sha256(self.public_key.read_bytes()).hexdigest()

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
            "apk",
            """
            import json
            import os
            import sys
            from pathlib import Path

            args = sys.argv[1:]
            with Path(os.environ["XRAY_MITM_APK_LOG"]).open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(args) + "\\n")

            if args == ["update"] and os.environ.get("FAKE_APK_UPDATE_FAIL") == "1":
                raise SystemExit(1)
            if args[:1] == ["add"] and os.environ.get("FAKE_APK_ADD_FAIL") == "1":
                raise SystemExit(1)
            if args[:1] == ["upgrade"] and os.environ.get("FAKE_APK_UPGRADE_FAIL") == "1":
                raise SystemExit(1)
            if args == ["add", "xray-mitm", "luci-app-xray-mitm"]:
                world = Path(os.environ["XRAY_MITM_APK_WORLD"])
                lines = [
                    line for line in world.read_text(encoding="utf-8").splitlines()
                    if not line.startswith("xray-mitm")
                    and not line.startswith("luci-app-xray-mitm")
                ]
                lines.extend(["xray-mitm", "luci-app-xray-mitm"])
                world.write_text("\\n".join(lines) + "\\n", encoding="utf-8")
            """,
        )

    def write_fake(self, name: str, body: str) -> None:
        path = self.bin_dir / name
        path.write_text(
            "#!/usr/bin/env python3\n" + textwrap.dedent(body).lstrip(),
            encoding="utf-8",
        )
        path.chmod(0o755)

    def run_installer(
        self,
        *,
        fake_uid: str = "0",
        key_sha256: str | None = None,
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.update(
            {
                "FAKE_UID": fake_uid,
                "PATH": f"{self.bin_dir}:{env['PATH']}",
                "XRAY_MITM_APK_KEYS_DIR": str(self.keys_dir),
                "XRAY_MITM_APK_LOG": str(self.apk_log),
                "XRAY_MITM_APK_WORLD": str(self.world_file),
                "XRAY_MITM_BACKUP_DIR": str(self.backup_dir),
                "XRAY_MITM_CONFIG_FILE": str(self.config_file),
                "XRAY_MITM_FEED_URL": FEED_URL,
                "XRAY_MITM_FIXTURES": str(self.fixtures),
                "XRAY_MITM_KEEP_DIR": str(self.keep_dir),
                "XRAY_MITM_OPENWRT_RELEASE_FILE": str(self.release_file),
                "XRAY_MITM_PUBLIC_KEY_SHA256": key_sha256 or self.public_key_sha256,
                "XRAY_MITM_PUBLIC_KEY_URL": f"https://fixtures.invalid/{KEY_NAME}",
                "XRAY_MITM_REPOSITORIES_DIR": str(self.repositories_dir),
                "XRAY_MITM_STATE_DIR": str(self.state_dir),
            }
        )
        if extra_env:
            env.update(extra_env)
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

    @property
    def installed_key(self) -> Path:
        return self.keys_dir / KEY_NAME

    @property
    def repository_file(self) -> Path:
        return self.repositories_dir / "xray-mitm.list"

    @property
    def keep_file(self) -> Path:
        return self.keep_dir / "xray-mitm-feed"

    def test_verified_key_configures_feed_and_installs_by_package_name(self) -> None:
        result = self.run_installer()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Authenticated installation/update complete.", result.stdout)
        self.assertIn(self.public_key_sha256, result.stdout)
        self.assertEqual(
            self.apk_calls(),
            [
                ["update"],
                ["add", "xray-mitm", "luci-app-xray-mitm"],
                ["upgrade", "xray-mitm", "luci-app-xray-mitm"],
            ],
        )
        self.assertEqual(self.installed_key.read_bytes(), self.public_key.read_bytes())
        self.assertEqual(self.repository_file.read_text(), FEED_URL + "\n")
        self.assertEqual(
            self.keep_file.read_text(),
            f"{self.installed_key}\n{self.repository_file}\n",
        )
        self.assertNotIn("--allow-untrusted", json.dumps(self.apk_calls()))
        self.assertIn("xray-mitm\n", self.world_file.read_text())
        self.assertIn("luci-app-xray-mitm\n", self.world_file.read_text())

    def test_fingerprint_mismatch_stops_before_system_changes(self) -> None:
        result = self.run_installer(key_sha256="0" * 64)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("fingerprint mismatch", result.stderr)
        self.assertEqual(self.apk_calls(), [])
        self.assertFalse(self.installed_key.exists())
        self.assertFalse(self.repository_file.exists())
        self.assertEqual(self.world_file.read_text(), "base-files\n")

    def test_private_key_marker_is_rejected(self) -> None:
        self.public_key.write_text(
            "-----BEGIN PUBLIC KEY-----\n"
            "-----BEGIN PRIVATE KEY-----\n"
            "-----END PRIVATE KEY-----\n",
            encoding="utf-8",
        )
        digest = hashlib.sha256(self.public_key.read_bytes()).hexdigest()

        result = self.run_installer(key_sha256=digest)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("private-key material", result.stderr)
        self.assertEqual(self.apk_calls(), [])

    def test_apk_update_failure_restores_previous_feed_and_world(self) -> None:
        self.installed_key.write_text("old key\n", encoding="utf-8")
        self.repository_file.write_text("https://old.invalid/packages.adb\n", encoding="utf-8")
        self.keep_file.write_text("old keep\n", encoding="utf-8")
        self.world_file.write_text("base-files\nxray-mitm=0.1.0-r4\n", encoding="utf-8")

        result = self.run_installer(extra_env={"FAKE_APK_UPDATE_FAIL": "1"})

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("previous feed state was restored", result.stderr)
        self.assertEqual(self.apk_calls(), [["update"]])
        self.assertEqual(self.installed_key.read_text(), "old key\n")
        self.assertEqual(
            self.repository_file.read_text(), "https://old.invalid/packages.adb\n"
        )
        self.assertEqual(self.keep_file.read_text(), "old keep\n")
        self.assertEqual(self.world_file.read_text(), "base-files\nxray-mitm=0.1.0-r4\n")

    def test_apk_add_failure_restores_previous_feed_and_world(self) -> None:
        previous_world = "base-files\nxray-mitm=0.1.0-r4\n"
        self.world_file.write_text(previous_world, encoding="utf-8")

        result = self.run_installer(extra_env={"FAKE_APK_ADD_FAIL": "1"})

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("previous feed and package-selection state was restored", result.stderr)
        self.assertEqual(
            self.apk_calls(),
            [["update"], ["add", "xray-mitm", "luci-app-xray-mitm"]],
        )
        self.assertFalse(self.installed_key.exists())
        self.assertFalse(self.repository_file.exists())
        self.assertFalse(self.keep_file.exists())
        self.assertEqual(self.world_file.read_text(), previous_world)

    def test_targeted_upgrade_failure_restores_previous_feed_and_world(self) -> None:
        previous_world = "base-files\nxray-mitm=0.1.0-r4\n"
        self.world_file.write_text(previous_world, encoding="utf-8")

        result = self.run_installer(extra_env={"FAKE_APK_UPGRADE_FAIL": "1"})

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Package upgrade failed", result.stderr)
        self.assertEqual(
            self.apk_calls(),
            [
                ["update"],
                ["add", "xray-mitm", "luci-app-xray-mitm"],
                ["upgrade", "xray-mitm", "luci-app-xray-mitm"],
            ],
        )
        self.assertFalse(self.installed_key.exists())
        self.assertFalse(self.repository_file.exists())
        self.assertFalse(self.keep_file.exists())
        self.assertEqual(self.world_file.read_text(), previous_world)

    def test_backup_is_private_and_contains_existing_state(self) -> None:
        self.config_file.write_text("config service 'main'\n", encoding="utf-8")
        (self.state_dir / "config.json").write_text("{}\n", encoding="utf-8")

        result = self.run_installer()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        backups = list(self.backup_dir.glob("xray-mitm-before-install-*.tar.gz"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].stat().st_mode & 0o777, 0o600)
        listing = subprocess.check_output(["tar", "-tzf", str(backups[0])], text=True)
        self.assertIn("xray-mitm", listing)
        self.assertIn("world", listing)

    def test_requires_root(self) -> None:
        result = self.run_installer(fake_uid="1000")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Run this installer as root", result.stderr)
        self.assertEqual(self.apk_calls(), [])

    def test_rejects_older_and_unpublished_release_series(self) -> None:
        for release in ("25.12.4", "25.13.0", "26.1.0"):
            with self.subTest(release=release):
                self.release_file.write_text(
                    f"DISTRIB_RELEASE='{release}'\n", encoding="utf-8"
                )
                if self.apk_log.exists():
                    self.apk_log.unlink()
                result = self.run_installer()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("official OpenWrt 25.12.5", result.stderr)
                self.assertEqual(self.apk_calls(), [])


if __name__ == "__main__":
    unittest.main()
