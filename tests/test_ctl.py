#!/usr/bin/env python3
"""Offline tests for the supported xray-mitmctl command boundary."""

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
CTL_SOURCE = PROJECT / "xray-mitm/files/usr/sbin/xray-mitmctl"
LIBEXEC_SOURCE = PROJECT / "xray-mitm/files/usr/libexec/xray-mitm"
DEFAULT_UCI = PROJECT / "xray-mitm/files/etc/config/xray-mitm"
SAMPLE = PROJECT / "xray-mitm/files/usr/share/xray-mitm/config.json.example"
FAKE_COMMAND = PROJECT / "tests/fakes/openwrt_cmd.py"


class ControlFixture(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(
            prefix="xray-mitm-ctl-tests-", dir="/tmp"
        )
        self.root = Path(self.temporary.name)
        for relative in (
            "etc/config", "etc/init.d", "fake-bin", "tmp", "var/lock",
            "usr/bin", "usr/sbin", "usr/libexec/xray-mitm", "usr/share/xray-mitm",
            "usr/share/v2ray",
        ):
            (self.root / relative).mkdir(parents=True, exist_ok=True)
        shutil.copyfile(DEFAULT_UCI, self.root / "etc/config/xray-mitm")
        uci_path = self.root / "etc/config/xray-mitm"
        uci_path.write_text(
            uci_path.read_text(encoding="utf-8").replace(
                "/usr/share/v2ray", str(self.root / "usr/share/v2ray")
            ),
            encoding="utf-8",
        )
        shutil.copyfile(SAMPLE, self.root / "usr/share/xray-mitm/config.json.example")
        self.ctl_path = self.root / "usr/sbin/xray-mitmctl"
        shutil.copyfile(CTL_SOURCE, self.ctl_path)
        self.ctl_path.chmod(0o755)
        for name in ("cert", "check", "config", "passwall2", "common.sh"):
            destination = self.root / "usr/libexec/xray-mitm" / name
            shutil.copyfile(LIBEXEC_SOURCE / name, destination)
            destination.chmod(0o644 if name == "common.sh" else 0o755)

        init = self.root / "etc/init.d/xray-mitm"
        init.write_text(
            "#!/bin/sh\n"
            "case \"${1:-}\" in\n"
            "  running) [ -e \"$XRAY_MITM_TEST_ROOT/tmp/running\" ] ;;\n"
            "  enabled) [ -e \"$XRAY_MITM_TEST_ROOT/tmp/boot-enabled\" ] ;;\n"
            "  start|restart)\n"
            "    [ \"${FAIL_START:-0}\" != 1 ] || exit 1\n"
            "    touch \"$XRAY_MITM_TEST_ROOT/tmp/running\"\n"
            "    printf '%s\\n' \"$1\" >>\"$XRAY_MITM_TEST_ROOT/tmp/actions\" ;;\n"
            "  stop) rm -f \"$XRAY_MITM_TEST_ROOT/tmp/running\" ;;\n"
            "  enable) touch \"$XRAY_MITM_TEST_ROOT/tmp/boot-enabled\" ;;\n"
            "  disable) rm -f \"$XRAY_MITM_TEST_ROOT/tmp/boot-enabled\" ;;\n"
            "  *) exit 64 ;;\n"
            "esac\n",
            encoding="utf-8",
        )
        init.chmod(0o755)

        xray = self.root / "usr/bin/xray"
        xray.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        xray.chmod(0o755)

        fake_bin = self.root / "fake-bin"
        for command in ("uci", "jsonfilter", "stat", "flock"):
            destination = fake_bin / command
            shutil.copyfile(FAKE_COMMAND, destination)
            destination.chmod(0o755)

        self.env = os.environ.copy()
        self.env["XRAY_MITM_TEST_ROOT"] = str(self.root)
        self.env["XRAY_MITM_LIBEXEC"] = str(self.root / "usr/libexec/xray-mitm")
        self.env["PATH"] = f"{fake_bin}:{self.env['PATH']}"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def ctl(self, *args: str, status: int = 0, env=None):
        result = subprocess.run(
            ["sh", str(self.ctl_path), *args], env=env or self.env, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        self.assertEqual(result.returncode, status, result.stdout + result.stderr)
        return result

    def test_fresh_setup_and_repeat_are_safe(self) -> None:
        first = json.loads(self.ctl("setup-recommended").stdout)
        self.assertTrue(first["ready"])
        self.assertTrue(first["config_created"])
        self.assertTrue(first["certificate_created"])
        self.assertTrue(first["certificate_activated"])
        self.assertTrue(first["service_started"])
        self.assertTrue(first["boot_enabled"])
        cert = self.root / "etc/xray-mitm/mycert.crt"
        key = self.root / "etc/xray-mitm/mycert.key"
        before = (hashlib.sha256(cert.read_bytes()).hexdigest(), key.resolve())

        second = json.loads(self.ctl("setup-recommended").stdout)
        self.assertTrue(second["ready"])
        self.assertFalse(second["changed"])
        self.assertEqual(before, (hashlib.sha256(cert.read_bytes()).hexdigest(), key.resolve()))
        self.assertEqual((self.root / "tmp/actions").read_text().splitlines(), ["start"])
        status = json.loads(self.ctl("setup-status-json").stdout)
        self.assertEqual(status["setup"], "ready")
        self.assertEqual(
            status["passwall2"],
            {
                "installed": False,
                "compatible": False,
                "shunt_available": False,
                "vpn_available": False,
            },
        )
        self.assertEqual(
            status["routing"],
            {
                "configured": False,
                "recommended_matches_current": False,
                "recovery_pending": False,
            },
        )
        self.assertEqual(status["health"], {"healthy": None})

    def test_existing_custom_config_is_preserved(self) -> None:
        config = self.root / "etc/xray-mitm/config.json"
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text('{"custom":"preserve-me"}\n', encoding="utf-8")
        original = config.read_bytes()
        self.assertTrue(json.loads(self.ctl("setup-recommended").stdout)["ready"])
        self.assertEqual(config.read_bytes(), original)

    def test_valid_legacy_certificate_pair_is_preserved(self) -> None:
        self.ctl("config-install-default")
        cert_dir = self.root / "etc/xray-mitm"
        key = cert_dir / "mycert.key"
        cert = cert_dir / "mycert.crt"
        subprocess.run(
            [
                "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                "-keyout", str(key), "-out", str(cert), "-days", "30",
                "-subj", "/CN=Existing-Legacy-CA",
            ],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        key.chmod(0o600)
        original = (hashlib.sha256(cert.read_bytes()).hexdigest(),
                    hashlib.sha256(key.read_bytes()).hexdigest())

        result = json.loads(self.ctl("setup-recommended").stdout)
        self.assertTrue(result["ready"])
        self.assertFalse(result["certificate_created"])
        self.assertEqual(
            original,
            (hashlib.sha256(cert.read_bytes()).hexdigest(),
             hashlib.sha256(key.read_bytes()).hexdigest()),
        )
        status = json.loads(self.ctl("setup-status-json").stdout)
        self.assertTrue(status["certificate"]["ready"])
        self.assertIsNotNone(status["certificate"]["fingerprint"])
        self.assertIsNotNone(status["certificate"]["expiry"])

    def test_manual_candidate_requires_attention(self) -> None:
        self.ctl("config-install-default")
        generated = json.loads(self.ctl("cert-generate", "Manual-Candidate", "365").stdout)
        result = json.loads(self.ctl("setup-recommended", status=1).stdout)
        self.assertEqual(result["error"], "candidate_requires_attention")
        cert_status = json.loads(self.ctl("cert-status-json").stdout)
        self.assertEqual(
            cert_status["slots"]["candidate"]["fingerprint"], generated["fingerprint"]
        )
        self.assertIsNone(cert_status["slots"]["current"])

    def test_invalid_legacy_certificate_files_require_attention(self) -> None:
        self.ctl("config-install-default")
        cert_dir = self.root / "etc/xray-mitm"
        (cert_dir / "mycert.crt").write_text("not a certificate\n", encoding="utf-8")
        key = cert_dir / "mycert.key"
        key.write_text("not a private key\n", encoding="utf-8")
        key.chmod(0o600)
        result = json.loads(self.ctl("setup-recommended", status=1).stdout)
        self.assertEqual(result["error"], "certificate_requires_attention")
        self.assertEqual((cert_dir / "mycert.crt").read_text(), "not a certificate\n")

    def test_unsafe_existing_config_is_not_replaced(self) -> None:
        config = self.root / "etc/xray-mitm/config.json"
        config.parent.mkdir(parents=True, exist_ok=True)
        config.touch()
        result = json.loads(self.ctl("setup-recommended", status=1).stdout)
        self.assertEqual(result["error"], "config_requires_attention")
        self.assertEqual(config.stat().st_size, 0)

    def test_start_failure_is_structured_and_recoverable(self) -> None:
        failed_env = self.env.copy()
        failed_env["FAIL_START"] = "1"
        failed = json.loads(
            self.ctl("setup-recommended", status=1, env=failed_env).stdout
        )
        self.assertEqual(failed["error"], "service_start_failed")
        self.assertTrue(failed["config_created"])
        self.assertTrue(failed["certificate_activated"])
        recovered = json.loads(self.ctl("setup-recommended").stdout)
        self.assertTrue(recovered["ready"])
        self.assertFalse(recovered["certificate_created"])

    def test_certificate_recovery_is_attempted_before_setup(self) -> None:
        recovery = self.root / "etc/xray-mitm/ca/recovery"
        recovery.parent.mkdir(parents=True, exist_ok=True)
        recovery.write_text("invalid recovery marker\n", encoding="utf-8")
        result = json.loads(self.ctl("setup-recommended", status=1).stdout)
        self.assertEqual(result["error"], "certificate_recovery_failed")
        self.assertFalse((self.root / "etc/xray-mitm/config.json").exists())

    def test_passwall2_namespace_and_rpcd_boundary(self) -> None:
        inspect = json.loads(self.ctl("passwall2", "inspect").stdout)
        self.assertFalse(inspect["available"])
        rejected = json.loads(
            self.ctl("passwall2", "apply", "not-a-token", status=1).stdout
        )
        self.assertIn("invalid passwall2", rejected["error"])
        rpc = (
            PROJECT / "luci-app-xray-mitm/root/usr/share/rpcd/ucode/xray-mitm.uc"
        ).read_text(encoding="utf-8")
        self.assertNotIn("/usr/libexec/xray-mitm/passwall2", rpc)
        self.assertIn("[ CTL, 'passwall2', 'inspect' ]", rpc)
        self.assertIn("[ CTL, 'passwall2', 'plan'", rpc)

    def test_passwall2_namespace_dispatches_every_supported_operation(self) -> None:
        helper = self.root / "usr/libexec/xray-mitm/passwall2"
        helper.write_text(
            "#!/bin/sh\n"
            "printf '%s\\n' \"$*\" >>\"$XRAY_MITM_TEST_ROOT/tmp/passwall-calls\"\n"
            "printf '%s\\n' '{\"ok\":true}'\n",
            encoding="utf-8",
        )
        helper.chmod(0o755)
        request = self.root / "tmp/request.json"
        request.write_text("{}\n", encoding="utf-8")
        token = "a" * 64
        for args in (
            ("inspect",), ("plan", str(request)), ("apply", token),
            ("rollback", token), ("recover",),
        ):
            self.assertTrue(json.loads(self.ctl("passwall2", *args).stdout)["ok"])
        self.assertEqual(
            (self.root / "tmp/passwall-calls").read_text().splitlines(),
            [
                "inspect", f"plan {request}", f"apply {token}",
                f"rollback {token}", "recover",
            ],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
