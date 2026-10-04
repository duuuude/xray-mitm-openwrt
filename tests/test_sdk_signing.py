#!/usr/bin/env python3
"""Offline contract tests; --sdk additionally executes disposable SDK regressions.

The real publisher shell blocks are exercised, not a copied signing transaction.
Only freshly generated keys and tiny unsigned packages are mounted. No release
artifacts, repository keys, protected environment or network are used by containers.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
import uuid


ROOT = Path(__file__).resolve().parents[1]
PUBLISHER = ROOT / ".github/workflows/publish-feed.yml"
COMPONENT = ROOT / ".github/workflows/signing-regression.yml"
SIGN_STEP = "Sign the exact package index without rebuilding packages"
CLEANUP_STEP = "Remove temporary private signing material"
APK = "/builder/staging_dir/host/bin/apk"
PIN = "ghcr.io/openwrt/sdk@sha256:d7759c08b2c0b0ffe57719bd8a293543708cbc27b18941478ebeae04c42986ed"
KEY_FILES = (
    "xray-mitm-feed-private.pem", "xray-mitm-feed-derived.pem",
    "xray-mitm-feed-derived.der", "xray-mitm-feed-committed.der",
)


def shell_block(document: str, name: str) -> str:
    """Accept one literal, fixed-indent run block in the known publisher format.

    This intentionally is not a general YAML interpreter. Ambiguous steps,
    folded scripts or format drift fail rather than silently testing old code.
    """
    marker = f"      - name: {name}\n"
    if document.count(marker) != 1:
        raise ValueError(f"Expected one publisher step: {name}")
    section = document.split(marker, 1)[1].split("\n      - ", 1)[0]
    if section.count("        run: |\n") != 1:
        raise ValueError(f"Expected one literal shell block: {name}")
    body = section.split("        run: |\n", 1)[1].rstrip("\n")
    if not body or any(line and not line.startswith("          ") for line in body.splitlines()):
        raise ValueError(f"Unsupported publisher shell indentation: {name}")
    return textwrap.dedent(body) + "\n"


def publisher_scripts() -> tuple[str, str]:
    document = PUBLISHER.read_text(encoding="utf-8")
    pins = re.findall(r"(?m)^  SDK_IMAGE: (\S+)$", document)
    if pins != [PIN]:
        raise ValueError("Publisher SDK pin changed; reconcile the component fixture pin.")
    return shell_block(document, SIGN_STEP), shell_block(document, CLEANUP_STEP)


class ContractTests(unittest.TestCase):
    def test_extracts_actual_offline_transaction_and_always_cleanup(self) -> None:
        signing, cleanup = publisher_scripts()
        self.assertIn("--network none", signing)
        self.assertIn("--user 0:0", signing)
        self.assertIn("cd /promotion", signing)
        self.assertEqual(signing.count("sha256sum -c PACKAGE_SHA256SUMS"), 2)
        self.assertIn(f"APK_BIN={APK}", signing)
        self.assertIn(f"{APK} --keys-dir /keys verify", signing)
        self.assertNotIn("--allow-untrusted", signing)
        document = PUBLISHER.read_text(encoding="utf-8")
        section = document.split(f"      - name: {CLEANUP_STEP}\n", 1)[1].split("\n      - ", 1)[0]
        self.assertIn("        if: always()", section)
        for name in KEY_FILES:
            self.assertIn(name, cleanup)

    def test_extractor_fails_on_missing_duplicate_or_folded_step(self) -> None:
        good = f"      - name: example\n        run: |\n          true\n"
        self.assertEqual(shell_block(good, "example"), "true\n")
        for bad in ("", good + good, good.replace("run: |", "run: >"), good.replace("          true", "        true")):
            with self.assertRaises(ValueError):
                shell_block(bad, "example")

    def test_component_is_secret_free_exact_head_and_path_scoped(self) -> None:
        text = COMPONENT.read_text(encoding="utf-8")
        self.assertIn("contents: read", text)
        self.assertIn("persist-credentials: false", text)
        self.assertIn("github.event.pull_request.head.sha || github.sha", text)
        self.assertIn("python3 tests/test_sdk_signing.py --sdk", text)
        self.assertIn(PIN, text)
        self.assertIn("timeout-minutes: 10", text)
        for forbidden in ("secrets.", "pull_request_target:", "environment:", "docs/**", "deploy-pages", "upload-artifact", "workflow_dispatch:"):
            self.assertNotIn(forbidden, text)
        for path in (".github/workflows/publish-feed.yml", ".github/workflows/signing-regression.yml", "scripts/sign-apk-index.sh", "tests/test_sdk_signing.py", "tests/test_signed_feed.py"):
            self.assertEqual(text.count(f'"{path}"'), 2)


class SDKTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.deadline = time.monotonic() + 420
        cls.signing, cls.cleanup = publisher_scripts()
        cls.docker = shutil.which("docker")
        if not cls.docker or not shutil.which("openssl") or not shutil.which("bash"):
            raise RuntimeError("Docker, OpenSSL and Bash are required; component result is BLOCKED, not skipped.")
        if "DOCKER_HOST" in os.environ or "DOCKER_CONTEXT" in os.environ:
            raise RuntimeError("Unset Docker endpoint/context overrides before testing.")
        cls.context = cls.command([cls.docker, "context", "show"]).stdout.strip()
        contexts = json.loads(cls.command([cls.docker, "context", "inspect", cls.context]).stdout)
        if (len(contexts) != 1 or contexts[0]["Name"] != cls.context or
                not contexts[0]["Endpoints"]["docker"]["Host"].startswith("unix:///")):
            raise RuntimeError("Disposable key tests require a local Unix-socket Docker context.")
        # Never let an offline test silently fetch an image, change the runtime,
        # or select a mutable SDK tag. CI pulls this exact digest beforehand.
        cls.command([cls.docker, "--context", cls.context, "image", "inspect", PIN])
        print("SDK component: exact cached digest; local Docker endpoint; disposable fixtures only.", flush=True)

    @classmethod
    def command(cls, args: list[str], *, env: dict[str, str] | None = None,
                expected: int | None = 0) -> subprocess.CompletedProcess[str]:
        remaining = cls.deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError("Disposable component elapsed budget exhausted.")
        result = subprocess.run(args, env=env, capture_output=True, text=True,
                                timeout=min(120, remaining), check=False)
        if expected is not None and result.returncode != expected:
            # Generated PEM material is never an argument or emitted in errors.
            raise AssertionError(f"Component command failed (exit {result.returncode}):\n{result.stdout}\n{result.stderr}")
        return result

    def remove_container(self, name: str) -> None:
        # Cleanup has its own bounded budget even when a test command times out.
        # Select only this invocation's random name, never a broad Docker prune.
        result = subprocess.run([
            self.docker, "--context", self.context, "ps", "--all",
            "--filter", f"name=^/{name}$", "--format", "{{.ID}}",
        ], capture_output=True, text=True, timeout=20, check=True)
        if result.stdout.strip():
            subprocess.run([self.docker, "--context", self.context, "rm", "--force", name],
                           capture_output=True, text=True, timeout=20, check=True)

    def container(self, script: str, *, user: str = "0:0") -> subprocess.CompletedProcess[str]:
        name = "xray-disposable-sdk-" + uuid.uuid4().hex
        try:
            return self.command([
                self.docker, "--context", self.context, "run", "--rm", "--pull=never",
                "--name", name,
                "--network", "none", "--user", user, "--cap-drop", "ALL",
                "--security-opt", "no-new-privileges", "--entrypoint", "/bin/sh",
                "-v", f"{self.workspace / 'promotion'}:/promotion",
                "-v", f"{self.payload}:/payload:ro",
                "-v", f"{self.workspace / 'keys'}:/keys:ro",
                "-v", f"{self.workspace / 'scripts/sign-apk-index.sh'}:/sign-apk-index.sh:ro",
                "-v", f"{self.runner}:/test-runner:ro", PIN, "-ceu", script,
            ], expected=None)
        finally:
            self.remove_container(name)

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="xray-disposable-sdk-")
        self.root = Path(self.temporary.name)
        self.workspace = self.root / "fixture-workspace"
        self.runner = self.root / "runner"
        self.payload = self.root / "payload"
        try:
            for path in (self.workspace / "promotion", self.workspace / "keys", self.workspace / "scripts", self.runner, self.payload):
                path.mkdir(parents=True, mode=0o755)
            # Container non-root users must be able to traverse the test mount;
            # private material remains mode 0600, never relaxed to 0644.
            self.runner.chmod(0o755)
            (self.payload / "fixture.txt").write_text("Disposable APK signing fixture; not a product package.\n")
            shutil.copyfile(ROOT / "scripts/sign-apk-index.sh", self.workspace / "scripts/sign-apk-index.sh")
            self.key = self.root / "disposable.pem"
            self.command(["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048", "-out", str(self.key)],
                         env=dict(os.environ, OPENSSL_CONF="/dev/null"))
            self.key.chmod(0o600)
            self.command(["openssl", "pkey", "-in", str(self.key), "-pubout", "-out", str(self.workspace / "keys/disposable.pem")])
            result = self.container(f"""
                cd /promotion
                for package in sdk-signing-core-fixture sdk-signing-luci-fixture; do
                    {APK} mkpkg --info name:$package --info version:1.0-r0 \
                        --info arch:all --info description:disposable --info license:MIT \
                        --files /payload --output "$package-1.0-r0.apk"
                done
                {APK} mkndx --allow-untrusted --output packages.adb *.apk
                chmod 0644 *.apk packages.adb
            """)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            promotion = self.workspace / "promotion"
            self.package = promotion / "sdk-signing-core-fixture-1.0-r0.apk"
            self.package_bytes = self.package.read_bytes()
            self.luci_package = promotion / "sdk-signing-luci-fixture-1.0-r0.apk"
            self.luci_bytes = self.luci_package.read_bytes()
            self.unsigned_index = (promotion / "packages.adb").read_bytes()
            self.manifest = "".join(hashlib.sha256(path.read_bytes()).hexdigest() + "  " + path.name + "\n"
                                    for path in (self.package, self.luci_package))
            (promotion / "PACKAGE_SHA256SUMS").write_text(self.manifest, encoding="ascii")
        except BaseException:
            self.temporary.cleanup()
            raise

    def tearDown(self) -> None:
        self.temporary.cleanup()
        self.assertFalse(self.root.exists(), "Disposable fixture/key directory was not removed.")

    def sign(self, script: str | None = None) -> subprocess.CompletedProcess[str]:
        # Use the unchanged publisher's *actual* shell and cleanup steps, with
        # synthetic workspace/key inputs. No committed public key is mounted.
        env = {name: value for name, value in os.environ.items()
               if name not in ("BASH_ENV", "ENV", "SHELLOPTS", "BASHOPTS", "DOCKER_HOST", "DOCKER_CONTEXT", "APK_PRIVATE_KEY")}
        env.update(GITHUB_WORKSPACE=str(self.workspace), RUNNER_TEMP=str(self.runner),
                   SDK_IMAGE=PIN, DOCKER_CONTEXT=self.context,
                   APK_PRIVATE_KEY=self.key.read_text(encoding="ascii"))
        for name in KEY_FILES[1:]:
            (self.runner / name).write_text("disposable derived-file sentinel\n")
        name = "xray-disposable-sdk-" + uuid.uuid4().hex
        signing = script or self.signing
        self.assertEqual(signing.count("docker run --rm"), 1)
        # Lifecycle instrumentation only: preserve all publisher flags/body,
        # but name the test container so a timed-out client cannot strand it.
        signing = signing.replace("docker run --rm", f"docker run --rm --pull=never --name {name}")
        try:
            return self.command(["bash", "-c", signing], env=env, expected=None)
        finally:
            try:
                self.remove_container(name)
            finally:
                subprocess.run(["bash", "-c", self.cleanup], env=env, capture_output=True,
                               text=True, timeout=20, check=True)
            self.assertTrue(all(not (self.runner / name).exists() for name in KEY_FILES),
                            "Publisher cleanup did not remove temporary signing material.")
            self.assertEqual(self.key.stat().st_mode & 0o777, 0o600)
            self.assertEqual(self.package.read_bytes(), self.package_bytes,
                             "Signing changed APK bytes.")
            self.assertEqual(self.luci_package.read_bytes(), self.luci_bytes,
                             "Signing changed LuCI APK bytes.")
            self.assertEqual((self.workspace / "promotion/PACKAGE_SHA256SUMS").read_text(), self.manifest)

    def test_success_strict_verification_readable_outputs_and_cleanup(self) -> None:
        unsigned = self.container(f"{APK} --keys-dir /keys verify /promotion/packages.adb")
        self.assertNotEqual(unsigned.returncode, 0, "Fixture must start unsigned.")
        result = self.sign()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.count(self.package.name + ": OK"), 2)
        self.assertNotEqual((self.workspace / "promotion/packages.adb").read_bytes(), self.unsigned_index)
        strict = self.container(f"{APK} --keys-dir /keys verify /promotion/packages.adb")
        self.assertEqual(strict.returncode, 0, strict.stdout + strict.stderr)
        readable = self.container("for path in /promotion/packages.adb /promotion/PACKAGE_SHA256SUMS /promotion/*.apk; do test -r \"$path\"; done", user="65534:65534")
        self.assertEqual(readable.returncode, 0, "Signed outputs must be readable by a non-root consumer.")

    def test_checksum_failure_stops_before_signing_and_cleans_up(self) -> None:
        self.package.write_bytes(self.package_bytes + b"tampered")
        # Preserve this intentional corruption as the input, never repair it in
        # the transaction; the manifest remains the original trusted value.
        self.package_bytes = self.package.read_bytes()
        result = self.sign()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FAILED", result.stdout + result.stderr)
        self.assertEqual((self.workspace / "promotion/packages.adb").read_bytes(), self.unsigned_index)

    def test_wrong_working_directory_is_detected_and_cleans_up(self) -> None:
        self.assertEqual(self.signing.count("cd /promotion"), 1)
        result = self.sign(self.signing.replace("cd /promotion", "cd /tmp"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("PACKAGE_SHA256SUMS", result.stderr)
        self.assertEqual((self.workspace / "promotion/packages.adb").read_bytes(), self.unsigned_index)

    def test_wrong_executable_path_is_detected_and_cleans_up(self) -> None:
        self.assertEqual(self.signing.count(f"APK_BIN={APK}"), 1)
        result = self.sign(self.signing.replace(f"APK_BIN={APK}", "APK_BIN=/staging_dir/host/bin/apk"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("apk executable is unavailable", result.stderr)
        self.assertEqual((self.workspace / "promotion/packages.adb").read_bytes(), self.unsigned_index)

    def test_nonowner_mode0600_key_is_not_made_world_readable(self) -> None:
        mounted = self.runner / KEY_FILES[0]
        shutil.copyfile(self.key, mounted)
        mounted.chmod(0o600)
        metadata = self.container(f"stat -c '%u %g %a' /test-runner/{KEY_FILES[0]}")
        self.assertEqual(metadata.returncode, 0, metadata.stderr)
        owner, group, mode = metadata.stdout.strip().split()
        self.assertNotEqual(owner, "65534", "Choose a verified non-owner UID, not a host mapping assumption.")
        self.assertEqual(mode, "600")
        print(f"Disposable key: host UID {mounted.stat().st_uid}; container UID/GID {owner}/{group}; mode {mode}; non-owner UID 65534.", flush=True)
        # access(2)/test -r can be misleading on desktop shared filesystems;
        # require an actual attempted read, discarding every byte locally.
        denied = self.container(f"dd if=/test-runner/{KEY_FILES[0]} of=/dev/null status=none", user="65534:65534")
        self.assertNotEqual(denied.returncode, 0,
                            "Host bind mount permits non-owner reads of mode-0600 key; "
                            "permissions qualification is BLOCKED here. Require native Linux CI, not a relaxed assertion.")
        self.assertIn("Permission denied", denied.stderr)
        # Remove index write permissions as an alternative reason for failure.
        # Only these synthetic output fixtures become writable, never the key.
        (self.workspace / "promotion").chmod(0o777)
        (self.workspace / "promotion/packages.adb").chmod(0o666)
        writable = self.container("test -w /promotion; test -w /promotion/packages.adb", user="65534:65534")
        self.assertEqual(writable.returncode, 0, writable.stderr)
        self.assertEqual(self.signing.count("--user 0:0"), 1)
        result = self.sign(self.signing.replace("--user 0:0", "--user 65534:65534"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Permission denied", result.stderr)
        self.assertNotIn("APK index signed.", result.stdout)
        self.assertEqual((self.workspace / "promotion/packages.adb").read_bytes(), self.unsigned_index)

    def test_mismatched_public_key_fails_strict_verification_and_cleans_up(self) -> None:
        wrong = self.root / "wrong-disposable.pem"
        self.command(["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048", "-out", str(wrong)])
        wrong.chmod(0o600)
        self.command(["openssl", "pkey", "-in", str(wrong), "-pubout", "-out", str(self.workspace / "keys/disposable.pem")])
        result = self.sign()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("APK index signed.", result.stdout)
        self.assertNotEqual((self.workspace / "promotion/packages.adb").read_bytes(), self.unsigned_index)
        strict = self.container(f"{APK} --keys-dir /keys verify /promotion/packages.adb")
        self.assertNotEqual(strict.returncode, 0)


if __name__ == "__main__":
    sdk = "--sdk" in sys.argv[1:]
    arguments = [value for value in sys.argv[1:] if value != "--sdk"]
    if arguments:
        raise SystemExit("Usage: python3 tests/test_sdk_signing.py [--sdk]")
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ContractTests)
    if sdk:
        suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(SDKTests))
    else:
        print("Offline contracts only; SDK execution NOT RUN (explicit --sdk required).", flush=True)
    raise SystemExit(0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1)
