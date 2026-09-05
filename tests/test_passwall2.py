#!/usr/bin/env python3
"""Offline integration tests for the transactional PassWall2 helper."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
HELPER = PROJECT / "xray-mitm/files/usr/libexec/xray-mitm/passwall2"
FAKE_COMMAND = PROJECT / "tests/fakes/openwrt_cmd.py"


BASE_CONFIG = """\
config global 'global'
\toption enabled '1'
\toption localhost_proxy '1'
\toption node 'main_shunt'

config nodes 'vpn_node'
\toption remarks 'Fixture VPN'
\toption type 'Xray'
\toption protocol 'vless'
\toption address 'private.fixture.invalid'
\toption uuid 'fixture-private-value-7391'

config nodes 'main_shunt'
\toption remarks 'Fixture shunt'
\toption type 'Xray'
\toption protocol '_shunt'
\toption shunt_group 'main_group'
\toption default_node 'vpn_node'
\toption existing_main '_direct'

config shunt_rules 'other_group_rule'
\toption remarks 'Other group stays in place'
\toption network 'tcp,udp'
\toption domain_list 'domain:other.fixture.invalid'
\toption group 'other_group'

config shunt_rules 'existing_main'
\toption remarks 'Existing main-group rule'
\toption network 'tcp,udp'
\toption domain_list 'domain:existing.fixture.invalid'
\toption group 'main_group'
"""


DEFAULT_REQUEST = {
    "shunt_node": "main_shunt",
    "vpn_node": "vpn_node",
    "lan_zone": "",
    "gemini": True,
    "android_check": True,
    "youtube_control": True,
    "google_mitm": True,
    "iran_direct": True,
    "accounts_google": True,
    "set_default_vpn": True,
    "set_global_shunt": False,
    "set_localhost_proxy_zero": True,
    "block_quic": False,
}


class PassWall2Fixture(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(
            prefix="xray-mitm-tests-", dir="/tmp"
        )
        self.root = Path(self.temporary.name)
        for relative in (
            "etc/config",
            "etc/init.d",
            "usr/share/passwall2",
            "tmp",
            "var/lock",
            "fake-bin",
        ):
            (self.root / relative).mkdir(parents=True, exist_ok=True)

        self.config = self.root / "etc/config/passwall2"
        self.config.write_text(BASE_CONFIG, encoding="utf-8")
        self.config.chmod(0o600)
        self.original = self.config.read_bytes()

        app = self.root / "usr/share/passwall2/app.sh"
        app.write_text("# fixture presence marker\n", encoding="utf-8")

        init = self.root / "etc/init.d/passwall2"
        init.write_text(
            "#!/bin/sh\n"
            "[ \"${1:-}\" = restart ] || exit 64\n"
            "printf 'restart\\n' >>\"$XRAY_MITM_TEST_ROOT/tmp/restarts\"\n",
            encoding="utf-8",
        )
        init.chmod(0o755)

        fake_bin = self.root / "fake-bin"
        for command in ("uci", "jsonfilter", "stat", "flock", "apk"):
            destination = fake_bin / command
            shutil.copyfile(FAKE_COMMAND, destination)
            destination.chmod(0o755)

        self.env = os.environ.copy()
        self.env["XRAY_MITM_TEST_ROOT"] = str(self.root)
        self.env["PATH"] = f"{fake_bin}:{self.env['PATH']}"
        self.request_counter = 0

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def helper(
        self, *arguments: str, expected_status: int = 0
    ) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
        result = subprocess.run(
            ["sh", str(HELPER), *arguments],
            env=self.env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(
            result.returncode,
            expected_status,
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        self.assertEqual(
            len(lines),
            1,
            f"helper must return exactly one JSON document; got {result.stdout!r}",
        )
        try:
            payload = json.loads(lines[0])
        except json.JSONDecodeError as exc:
            self.fail(f"helper returned invalid JSON: {exc}: {result.stdout!r}")
        self.assertIsInstance(payload, dict)
        return result, payload

    def request_file(self, overrides: dict[str, object] | None = None) -> Path:
        self.request_counter += 1
        suffix = f"T{self.request_counter:05d}"
        request_dir = self.root / "tmp" / f"xray-mitm-plan.{suffix}"
        request_dir.mkdir(mode=0o700)
        request = request_dir / "request.json"
        body = dict(DEFAULT_REQUEST)
        if overrides:
            body.update(overrides)
        request.write_text(json.dumps(body), encoding="utf-8")
        request.chmod(0o600)
        return request

    def uci(self, action: str, reference: str) -> str:
        result = subprocess.run(
            ["uci", "-c", str(self.config.parent), "-q", action, reference],
            env=self.env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.rstrip("\n")

    def restart_count(self) -> int:
        path = self.root / "tmp/restarts"
        return len(path.read_text(encoding="utf-8").splitlines()) if path.exists() else 0

    def plan_all(self) -> dict[str, object]:
        _, payload = self.helper("plan", str(self.request_file()))
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["no_change"])
        return payload

    def test_inspect_returns_only_non_secret_inventory(self) -> None:
        _, payload = self.helper("inspect")

        self.assertTrue(payload["ok"])
        self.assertTrue(payload["available"])
        self.assertTrue(payload["compatible"])
        self.assertTrue(payload["writable"])
        self.assertEqual(payload["package_manager"], "apk")
        self.assertEqual(payload["selected_shunt"], "main_shunt")
        self.assertEqual(payload["selected_vpn"], "vpn_node")
        serialized = json.dumps(payload, sort_keys=True)
        self.assertNotIn("fixture-private-value-7391", serialized)
        self.assertNotIn("private.fixture.invalid", serialized)
        self.assertNotIn("uuid", serialized.lower())
        self.assertEqual(self.config.read_bytes(), self.original)
        self.assertEqual(self.restart_count(), 0)

    def test_plan_apply_and_exact_rollback(self) -> None:
        plan = self.plan_all()
        token = str(plan["token"])

        self.assertEqual(self.config.read_bytes(), self.original)
        operation_kinds = [item["kind"] for item in plan["operations"]]
        self.assertEqual(
            operation_kinds[:6],
            [
                "upsert_local_socks_node",
                "upsert_rule",
                "upsert_rule",
                "upsert_rule",
                "upsert_rule",
                "upsert_rule",
            ],
        )
        staged = (
            self.root
            / "tmp/xray-mitm-passwall2-plans"
            / f"{token}.stage/config/passwall2"
        )
        staged_text = staged.read_text(encoding="utf-8")
        youtube_domains = self._uci_from_path(
            staged.parent, "get", "passwall2.xray_mitm_youtube.domain_list"
        )
        self.assertNotIn("googlevideo.com", youtube_domains)
        self.assertNotIn("googlevideo.com", staged_text)
        self.assertEqual(
            youtube_domains.splitlines(),
            [
                "domain:www.youtube.com",
                "domain:youtubei.googleapis.com",
                "domain:youtube.googleapis.com",
                "domain:accounts.youtube.com",
            ],
        )
        staged_order = self._section_order(staged.parent)
        managed_order = [
            "xray_mitm_gemini",
            "xray_mitm_android",
            "xray_mitm_youtube",
            "xray_mitm_google",
            "xray_mitm_ir",
        ]
        self.assertEqual(
            [name for name in staged_order if name in managed_order], managed_order
        )
        self.assertLess(
            staged_order.index("xray_mitm_ir"), staged_order.index("existing_main")
        )

        _, applied = self.helper("apply", token)
        self.assertTrue(applied["ok"])
        self.assertTrue(applied["changed"])
        self.assertEqual(applied["transaction"], token)
        self.assertTrue(applied["rollback_available"])
        self.assertEqual(self.restart_count(), 1)
        self.assertEqual(self.uci("get", "passwall2.@global[0].localhost_proxy"), "0")
        self.assertEqual(self.uci("get", "passwall2.xray_mitm_socks.address"), "127.0.0.1")
        self.assertEqual(self.uci("get", "passwall2.xray_mitm_socks.port"), "10808")
        self.assertEqual(self.uci("get", "passwall2.main_shunt.xray_mitm_google"), "xray_mitm_socks")
        self.assertEqual(self.uci("get", "passwall2.main_shunt.xray_mitm_ir"), "_direct")
        self.assertEqual(self.uci("get", "passwall2.xray_mitm_ir.network"), "tcp,udp")
        self.assertEqual(self.uci("get", "passwall2.xray_mitm_ir.ip_list"), "geoip:ir")
        self.assertEqual(self.uci("get", "passwall2.xray_mitm_gemini.network"), "tcp")
        self.assertIn(
            "domain:accounts.google.com",
            self.uci("get", "passwall2.xray_mitm_gemini.domain_list"),
        )

        _, rolled_back = self.helper("rollback", token)
        self.assertTrue(rolled_back["ok"])
        self.assertTrue(rolled_back["rolled_back"])
        self.assertEqual(self.restart_count(), 2)
        self.assertEqual(self.config.read_bytes(), self.original)
        state = self.root / "etc/xray-mitm/passwall2-routing"
        self.assertFalse((state / "recovery").exists())
        self.assertFalse((state / "last-transaction").exists())
        self.assertFalse((state / "backups" / f"{token}.passwall2").exists())
        self.assertFalse((state / "transactions" / f"{token}.meta").exists())

    def test_pending_changes_refuse_plan_without_touching_live_file(self) -> None:
        for package in ("passwall2", "firewall"):
            with self.subTest(package=package):
                pending = self.config.parent / f".pending-{package}"
                pending.write_text("fixture\n", encoding="utf-8")
                _, payload = self.helper(
                    "plan", str(self.request_file()), expected_status=73
                )
                self.assertFalse(payload["ok"])
                self.assertEqual(payload["error"], "pending_changes")
                self.assertEqual(self.config.read_bytes(), self.original)
                self.assertEqual(self.restart_count(), 0)
                pending.unlink()

    def test_plan_recovers_an_interrupted_apply_before_previewing(self) -> None:
        token = "a" * 64
        state = self.root / "etc/xray-mitm/passwall2-routing"
        backup_dir = state / "backups"
        tx_dir = state / "transactions"
        for directory in (self.root / "etc/xray-mitm", state, backup_dir, tx_dir):
            directory.mkdir(mode=0o700, exist_ok=True)
            directory.chmod(0o700)

        backup = backup_dir / f"{token}.passwall2"
        backup.write_bytes(self.original)
        backup.chmod(0o600)
        self.config.write_text(
            BASE_CONFIG.replace("option localhost_proxy '1'", "option localhost_proxy '0'"),
            encoding="utf-8",
        )
        self.config.chmod(0o600)
        interrupted = self.config.read_bytes()
        (tx_dir / f"{token}.meta").write_text(
            "schema=passwall2-uci-v1\n"
            f"pre_hash={hashlib.sha256(self.original).hexdigest()}\n"
            f"post_hash={hashlib.sha256(self.config.read_bytes()).hexdigest()}\n",
            encoding="utf-8",
        )
        (state / "last-transaction").write_text(f"{token}\n", encoding="utf-8")
        marker = state / "recovery"
        marker.write_text(
            "version=2\n"
            "kind=apply\n"
            f"token={token}\n"
            f"restore_hash={hashlib.sha256(self.original).hexdigest()}\n"
            "previous_token=\n",
            encoding="utf-8",
        )
        marker.chmod(0o600)

        _, inspection = self.helper("inspect")
        self.assertTrue(inspection["ok"])
        self.assertTrue(inspection["recovery_pending"])
        self.assertFalse(inspection["writable"])
        self.assertEqual(self.config.read_bytes(), interrupted)
        self.assertEqual(self.restart_count(), 0)
        self.assertTrue(marker.exists())

        _, payload = self.helper("plan", str(self.request_file()))
        self.assertTrue(payload["ok"])
        self.assertEqual(self.config.read_bytes(), self.original)
        self.assertEqual(self.restart_count(), 1)
        self.assertFalse(marker.exists())
        self.assertFalse(backup.exists())
        self.assertFalse((tx_dir / f"{token}.meta").exists())
        self.assertFalse((state / "last-transaction").exists())

    def _uci_from_path(self, config_dir: Path, action: str, reference: str) -> str:
        result = subprocess.run(
            ["uci", "-c", str(config_dir), "-q", action, reference],
            env=self.env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.rstrip("\n")

    def _section_order(self, config_dir: Path) -> list[str]:
        output = self._uci_from_path(config_dir, "show", "passwall2")
        return [line.split("=", 1)[0].split(".", 1)[1] for line in output.splitlines()]


if __name__ == "__main__":
    unittest.main(verbosity=2)
