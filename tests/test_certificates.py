#!/usr/bin/env python3
"""Offline certificate lifecycle tests using real OpenSSL and temporary storage."""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
HELPER = PROJECT / "xray-mitm/files/usr/libexec/xray-mitm/cert"
LIBEXEC = PROJECT / "xray-mitm/files/usr/libexec/xray-mitm"
DEFAULT_UCI = PROJECT / "xray-mitm/files/etc/config/xray-mitm"
FAKE_COMMAND = PROJECT / "tests/fakes/openwrt_cmd.py"


class CertificateFixture(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(
            prefix="xray-mitm-cert-tests-", dir="/tmp"
        )
        self.root = Path(self.temporary.name)
        for relative in ("etc/config", "etc/init.d", "fake-bin", "tmp", "var/lock"):
            (self.root / relative).mkdir(parents=True, exist_ok=True)

        shutil.copyfile(DEFAULT_UCI, self.root / "etc/config/xray-mitm")
        init = self.root / "etc/init.d/xray-mitm"
        init.write_text(
            "#!/bin/sh\n"
            "[ \"${1:-}\" = running ] && exit 1\n"
            "exit 0\n",
            encoding="utf-8",
        )
        init.chmod(0o755)

        fake_bin = self.root / "fake-bin"
        for command in ("uci", "stat", "flock"):
            destination = fake_bin / command
            shutil.copyfile(FAKE_COMMAND, destination)
            destination.chmod(0o755)

        self.env = os.environ.copy()
        self.env["XRAY_MITM_TEST_ROOT"] = str(self.root)
        self.env["XRAY_MITM_LIBEXEC"] = str(LIBEXEC)
        self.env["PATH"] = f"{fake_bin}:{self.env['PATH']}"
        self.import_dirs: list[Path] = []

    def tearDown(self) -> None:
        for directory in self.import_dirs:
            shutil.rmtree(directory, ignore_errors=True)
        self.temporary.cleanup()

    def helper(
        self, *arguments: str, expected_status: int = 0
    ) -> subprocess.CompletedProcess[str]:
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
        return result

    def generate(self, name: str = "MITM-Test-CA") -> tuple[str, Path]:
        result = self.helper("generate", name, "365")
        fingerprint = result.stdout.strip()
        self.assertRegex(fingerprint, r"^[a-f0-9]{64}$")
        candidate = self.root / "etc/xray-mitm/ca/candidate"
        self.assertTrue(candidate.is_symlink())
        slot = candidate.parent / os.readlink(candidate)
        return fingerprint, slot

    def import_dir(self, cert: Path, key: Path) -> Path:
        directory = Path(tempfile.mkdtemp(prefix="xray-mitm-rpc.", dir="/tmp"))
        self.import_dirs.append(directory)
        directory.chmod(0o700)
        shutil.copyfile(cert, directory / "input.crt")
        shutil.copyfile(key, directory / "input.key")
        (directory / "input.crt").chmod(0o600)
        (directory / "input.key").chmod(0o600)
        return directory

    def legacy_pair(self, usage: str | None = None) -> tuple[Path, Path]:
        directory = self.root / "etc/xray-mitm"
        directory.mkdir(exist_ok=True)
        cert, key = directory / "mycert.crt", directory / "mycert.key"
        config = self.root / "tmp/openssl.cnf"
        config.write_text(
            "[req]\ndistinguished_name=dn\nx509_extensions=ca\nprompt=no\n"
            "[dn]\nCN=Legacy-Test-CA\n[ca]\nbasicConstraints=critical,CA:TRUE\n"
            + (f"keyUsage=critical,{usage}\n" if usage else ""),
            encoding="ascii",
        )
        subprocess.run(
            ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
             "-days", "365", "-config", str(config), "-keyout", str(key),
             "-out", str(cert)],
            env=self.env, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        key.chmod(0o600)
        return cert, key

    def test_legacy_without_key_usage_adopts_and_remains_valid(self) -> None:
        cert, key = self.legacy_pair()
        original = cert.read_bytes()
        result = self.helper("adopt-legacy")
        self.assertRegex(result.stdout.strip(), r"^[a-f0-9]{64}$")
        self.assertTrue(cert.is_symlink())
        self.assertEqual(cert.read_bytes(), original)
        self.assertEqual(stat.S_IMODE(key.stat().st_mode), 0o600)
        self.helper("validate-current")
        status = json.loads(self.helper("status-json").stdout)
        self.assertTrue(status["managed"])
        self.assertFalse(status["recovery_pending"])

    def test_explicit_signing_prohibition_rejects_without_changing_pair(self) -> None:
        cert, key = self.legacy_pair("digitalSignature")
        original_cert, original_key = cert.read_bytes(), key.read_bytes()
        result = self.helper("adopt-legacy", expected_status=1)
        self.assertIn("does not permit certificate signing", result.stderr)
        self.assertFalse(cert.is_symlink())
        self.assertEqual(cert.read_bytes(), original_cert)
        self.assertEqual(key.read_bytes(), original_key)

    def test_generate_activate_and_export_public_only(self) -> None:
        fingerprint, slot = self.generate()
        certificate = slot / "mycert.crt"
        private_key = slot / "mycert.key"

        self.assertEqual(stat.S_IMODE(certificate.stat().st_mode), 0o644)
        self.assertEqual(stat.S_IMODE(private_key.stat().st_mode), 0o600)
        self.assertNotIn("PRIVATE KEY", certificate.read_text(encoding="ascii"))
        self.assertIn("PRIVATE KEY", private_key.read_text(encoding="ascii"))

        status_result = self.helper("status-json")
        status = json.loads(status_result.stdout)
        self.assertEqual(status["slots"]["candidate"]["fingerprint"], fingerprint)
        self.assertNotIn("PRIVATE KEY", status_result.stdout)
        exported = self.helper("export", "candidate").stdout
        self.assertEqual(exported, certificate.read_text(encoding="ascii"))
        self.assertNotIn("PRIVATE KEY", exported)

        self.helper("activate", fingerprint)
        ca_dir = self.root / "etc/xray-mitm/ca"
        self.assertTrue((ca_dir / "current").is_symlink())
        self.assertFalse((ca_dir / "candidate").exists())
        self.assertEqual(
            os.readlink(self.root / "etc/xray-mitm/mycert.crt"),
            "ca/current/mycert.crt",
        )
        self.assertEqual(
            os.readlink(self.root / "etc/xray-mitm/mycert.key"),
            "ca/current/mycert.key",
        )
        self.assertNotIn("PRIVATE KEY", self.helper("export", "current").stdout)

    def test_matching_import_succeeds_and_mismatched_key_is_rejected(self) -> None:
        first_fingerprint, first_slot = self.generate("MITM-Import-A")
        saved_cert = self.root / "tmp/import-a.crt"
        saved_key = self.root / "tmp/import-a.key"
        shutil.copyfile(first_slot / "mycert.crt", saved_cert)
        shutil.copyfile(first_slot / "mycert.key", saved_key)
        self.helper("discard", first_fingerprint)

        matching = self.import_dir(saved_cert, saved_key)
        imported = self.helper("prepare-import", str(matching)).stdout.strip()
        self.assertEqual(imported, first_fingerprint)
        self.assertFalse(matching.exists())
        self.helper("discard", imported)

        second_fingerprint, second_slot = self.generate("MITM-Import-B")
        second_key = self.root / "tmp/import-b.key"
        shutil.copyfile(second_slot / "mycert.key", second_key)
        self.helper("discard", second_fingerprint)

        mismatched = self.import_dir(saved_cert, second_key)
        rejected = self.helper("prepare-import", str(mismatched), expected_status=1)
        self.assertRegex(rejected.stderr, re.compile(r"do not match", re.IGNORECASE))
        self.assertFalse(mismatched.exists())
        self.assertFalse((self.root / "etc/xray-mitm/ca/candidate").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
