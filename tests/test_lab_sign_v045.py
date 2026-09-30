#!/usr/bin/env python3
"""Safety tests for the pinned local v0.4.5 lab-sign helper.

These tests use synthetic ZIP contents and a fake signing runner. They never
read a real signing key and do not perform cryptographic signing.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import lab_sign_v045 as lab  # noqa: E402


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_archive(
    *,
    source_commit: str | None = None,
    extra: dict[str, bytes] | None = None,
    package_checksum_override: bytes | None = None,
) -> bytes:
    core, luci = lab.PACKAGE_NAMES
    files = {
        "ARTIFACT_PURPOSE": b"promotable unsigned APK bundle\n",
        "BUILD_EVENT": b"push\n",
        "BUILD_RUN_ID": f"{lab.SOURCE_RUN_ID}\n".encode(),
        "BUILD_WORKFLOW": b"Build OpenWrt APKs\n",
        "OPENWRT_RELEASE": f"{lab.OPENWRT_RELEASE}\n".encode(),
        "PACKAGE_FORMAT": b"apk\n",
        "PACKAGES": f"{luci}\n{core}\n".encode(),
        "SDK_ARCH": f"{lab.SDK_ARCH}\n".encode(),
        "SOURCE_COMMIT": f"{source_commit or lab.SOURCE_COMMIT}\n".encode(),
        "packages.adb": b"synthetic unsigned index\n",
        core: b"synthetic core APK\n",
        luci: b"synthetic LuCI APK\n",
        "LICENSE": b"synthetic license\n",
        "README.fa.md": b"synthetic fa readme\n",
        "README.md": b"synthetic readme\n",
        "THIRD_PARTY_NOTICES.md": b"synthetic notices\n",
        "install.sh": b"#!/bin/sh\nexit 0\n",
    }
    files.update(extra or {})
    files["PACKAGE_SHA256SUMS"] = "".join(
        f"{sha256(files[name])}  {name}\n" for name in sorted((core, luci))
    ).encode("ascii")
    if package_checksum_override is not None:
        files["PACKAGE_SHA256SUMS"] = package_checksum_override
    files["SHA256SUMS"] = "".join(
        f"{sha256(files[name])}  {name}\n"
        for name in sorted((core, luci, "packages.adb"))
    ).encode("ascii")
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, contents in files.items():
            archive.writestr(name, contents)
    return target.getvalue()


def source_run() -> dict[str, object]:
    return {
        "id": lab.SOURCE_RUN_ID,
        "workflow_id": lab.SOURCE_WORKFLOW_ID,
        "status": "completed",
        "conclusion": "success",
        "event": "push",
        "run_attempt": 1,
        "head_branch": "main",
        "head_sha": lab.SOURCE_COMMIT,
        "repository": {"full_name": lab.REPOSITORY},
    }


def source_artifact(archive: bytes) -> dict[str, object]:
    return {
        "id": lab.SOURCE_ARTIFACT_ID,
        "name": lab.SOURCE_ARTIFACT_NAME,
        "digest": "sha256:" + sha256(archive),
        "expired": False,
        "size_in_bytes": len(archive),
        "workflow_run": {
            "id": lab.SOURCE_RUN_ID,
            "head_branch": "main",
            "head_sha": lab.SOURCE_COMMIT,
        },
    }


class LabSignV045Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.verified_source_package_sha256s = lab.SOURCE_PACKAGE_SHA256SUMS
        synthetic_hashes = {
            lab.PACKAGE_NAMES[0]: sha256(b"synthetic core APK\n"),
            lab.PACKAGE_NAMES[1]: sha256(b"synthetic LuCI APK\n"),
        }
        synthetic_manifest = "".join(
            f"{synthetic_hashes[name]}  {name}\n" for name in sorted(synthetic_hashes)
        ).encode("ascii")
        package_manifest_patch = mock.patch.object(
            lab, "SOURCE_PACKAGE_SHA256SUMS", synthetic_manifest
        )
        package_manifest_patch.start()
        self.addCleanup(package_manifest_patch.stop)
        self.archive = make_archive()
        self.digest = "sha256:" + sha256(self.archive)
        self.run = source_run()
        self.artifact = source_artifact(self.archive)

    def json_reader(self, _path: str) -> dict[str, object]:
        if _path.endswith("/artifacts?per_page=100"):
            return {"artifacts": [self.artifact]}
        return self.run

    def pinned_digest(self):
        return mock.patch.object(lab, "SOURCE_ARTIFACT_DIGEST", self.digest)

    def test_accepts_only_exact_live_run_and_artifact_identity(self) -> None:
        with self.pinned_digest():
            run, artifact = lab.verify_live_source(self.json_reader)
            self.assertEqual(run["head_sha"], lab.SOURCE_COMMIT)
            self.assertEqual(artifact["id"], lab.SOURCE_ARTIFACT_ID)

    def test_pins_the_verified_current_main_build_and_package_manifest(self) -> None:
        self.assertEqual(lab.SOURCE_RUN_ID, 36783895086)
        self.assertEqual(lab.SOURCE_WORKFLOW_ID, 351137159)
        self.assertEqual(lab.SOURCE_COMMIT, "c5fb835e2b6b862f6a1667441b3fcb8d1f51b0a7")
        self.assertEqual(lab.SOURCE_ARTIFACT_ID, 11130096816)
        self.assertEqual(
            lab.SOURCE_ARTIFACT_NAME,
            "xray-mitm-openwrt-25.12.5-aarch64_generic-"
            "c5fb835e2b6b862f6a1667441b3fcb8d1f51b0a7",
        )
        self.assertEqual(
            lab.SOURCE_ARTIFACT_DIGEST,
            "sha256:faaef49365a1715cc7393025c108cde471d3d96d5603f3ffb0d253423c983c4c",
        )
        self.assertEqual(
            lab.PACKAGE_NAMES,
            (
                "luci-app-xray-mitm-26.269.77380~a3bf576.apk",
                "xray-mitm-0.4.5-r1.apk",
            ),
        )
        self.assertEqual(
            self.verified_source_package_sha256s,
            b"f23b7c176deba7fad69d38f5cdd2f1ee31fe0071ddeb81897d65503503726f4a  "
            b"luci-app-xray-mitm-26.269.77380~a3bf576.apk\n"
            b"a03f2758867ddc38eb6ace592b57bea300b4f58913f0dfb19497296a7de71f8d  "
            b"xray-mitm-0.4.5-r1.apk\n",
        )

    def test_rejects_each_wrong_run_gate(self) -> None:
        mutations = {
            "status": "in_progress",
            "conclusion": "failure",
            "event": "workflow_dispatch",
            "run_attempt": 2,
            "head_branch": "feature",
            "head_sha": "f" * 40,
            "workflow_id": 1,
            "repository": {"full_name": "someone/else"},
        }
        with self.pinned_digest():
            for field, value in mutations.items():
                with self.subTest(field=field):
                    run = dict(self.run)
                    run[field] = value
                    with self.assertRaises(lab.LabSignError):
                        lab.verify_run_record(run)

    def test_rejects_missing_duplicate_or_mismatched_artifact(self) -> None:
        with self.pinned_digest():
            for items in ([], [self.artifact, self.artifact]):
                with self.subTest(count=len(items)):
                    with self.assertRaises(lab.LabSignError):
                        lab.verify_artifact_record({"artifacts": items}, self.run)
            for field, value in (
                ("name", "wrong-name"),
                ("digest", "sha256:" + "0" * 64),
                ("expired", True),
                ("size_in_bytes", 0),
            ):
                with self.subTest(field=field):
                    item = dict(self.artifact)
                    item[field] = value
                    with self.assertRaises(lab.LabSignError):
                        lab.verify_artifact_record({"artifacts": [item]}, self.run)

    def test_rejects_wrong_artifact_run_binding(self) -> None:
        with self.pinned_digest():
            item = dict(self.artifact)
            item["workflow_run"] = {"id": lab.SOURCE_RUN_ID + 1}
            with self.assertRaisesRegex(lab.LabSignError, "run binding"):
                lab.verify_artifact_record({"artifacts": [item]}, self.run)

    def test_signer_source_requires_clean_live_main(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"
            root.mkdir()
            subprocess.run(["git", "-C", str(root), "init", "-b", "main"], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.invalid"], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.name", "Lab Sign Test"], check=True)
            (root / "tool.py").write_text("synthetic\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "tool.py"], check=True)
            subprocess.run(["git", "-C", str(root), "commit", "-m", "fixture"], check=True, capture_output=True)
            head = subprocess.run(
                ["git", "-C", str(root), "rev-parse", "HEAD"],
                check=True,
                text=True,
                capture_output=True,
            ).stdout.strip()
            verify_main = lambda _path: {"sha": head}
            self.assertEqual(
                lab.verify_tool_source(verify_main, root=root, tracked_paths=("tool.py",)),
                head,
            )
            (root / "dirty.txt").write_text("uncommitted\n", encoding="utf-8")
            with self.assertRaisesRegex(lab.LabSignError, "dirty"):
                lab.verify_tool_source(verify_main, root=root, tracked_paths=("tool.py",))
            (root / "dirty.txt").unlink()
            with self.assertRaisesRegex(lab.LabSignError, "exactly match"):
                lab.verify_tool_source(
                    lambda _path: {"sha": "0" * 40},
                    root=root,
                    tracked_paths=("tool.py",),
                )
            subprocess.run(
                ["git", "-C", str(root), "update-index", "--assume-unchanged", "tool.py"],
                check=True,
            )
            (root / "tool.py").write_text("silently changed\n", encoding="utf-8")
            with self.assertRaisesRegex(lab.LabSignError, "differs from live main"):
                lab.verify_tool_source(verify_main, root=root, tracked_paths=("tool.py",))
            subprocess.run(["git", "-C", str(root), "checkout", "-b", "feature"], check=True, capture_output=True)
            with self.assertRaisesRegex(lab.LabSignError, "main checkout"):
                lab.verify_tool_source(verify_main, root=root, tracked_paths=("tool.py",))

    def test_reads_exact_pinned_archive_and_rejects_archive_digest_mismatch(self) -> None:
        with self.pinned_digest():
            files = lab._read_archive(self.archive)
            self.assertEqual(files["packages.adb"], b"synthetic unsigned index\n")
            with self.assertRaisesRegex(lab.LabSignError, "digest"):
                lab._read_archive(self.archive + b"tampered")

    def test_binary_api_download_is_streamed_with_a_hard_size_limit(self) -> None:
        class OversizedStream:
            def __init__(self) -> None:
                self.remaining = lab.MAX_ARCHIVE_BYTES + 4096
                self.bytes_read = 0
                self.read_sizes: list[int] = []

            def read(self, size: int) -> bytes:
                self.read_sizes.append(size)
                count = min(size, self.remaining)
                self.remaining -= count
                self.bytes_read += count
                return b"x" * count

            def close(self) -> None:
                pass

        class FakeProcess:
            def __init__(self) -> None:
                self.stdout = OversizedStream()
                self.killed = False
                self.returncode: int | None = None

            def kill(self) -> None:
                self.killed = True

            def poll(self) -> int | None:
                return self.returncode

            def wait(self) -> int:
                self.returncode = -9 if self.killed else 0
                return self.returncode

        process = FakeProcess()
        with mock.patch.object(lab.subprocess, "Popen", return_value=process) as popen:
            with self.assertRaisesRegex(lab.LabSignError, "exceeds the safe archive size limit"):
                lab._gh_api("repos/example/artifact.zip", binary=True)
        self.assertTrue(process.killed)
        self.assertEqual(process.stdout.bytes_read, lab.MAX_ARCHIVE_BYTES + 1)
        self.assertLessEqual(max(process.stdout.read_sizes), lab.MAX_API_READ_CHUNK)
        popen.assert_called_once_with(
            ["gh", "api", "repos/example/artifact.zip"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )

    def test_rejects_wrong_source_metadata_unknown_entries_and_duplicates(self) -> None:
        wrong_source = make_archive(source_commit="f" * 40)
        unknown = make_archive(extra={"surprise.txt": b"unexpected"})
        duplicate = io.BytesIO()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(duplicate, "w") as archive:
                for name, value in (("README.md", b"one"), ("README.md", b"two")):
                    archive.writestr(name, value)
        with self.pinned_digest():
            for payload in (wrong_source, unknown, duplicate.getvalue()):
                with self.subTest(size=len(payload)):
                    with mock.patch.object(lab, "SOURCE_ARTIFACT_DIGEST", "sha256:" + sha256(payload)):
                        with self.assertRaises(lab.LabSignError):
                            lab._read_archive(payload)

    def test_rejects_a_different_package_checksum_manifest(self) -> None:
        bad_archive = make_archive(
            package_checksum_override=(
                b"0" * 64 + b"  " + lab.PACKAGE_NAMES[0].encode("ascii") + b"\n"
            )
        )
        with mock.patch.object(lab, "SOURCE_ARTIFACT_DIGEST", "sha256:" + sha256(bad_archive)):
            with self.assertRaisesRegex(lab.LabSignError, "package checksums"):
                lab._read_archive(bad_archive)

    def test_prepare_creates_private_verified_session(self) -> None:
        with self.pinned_digest():
            root = lab.prepare_session(
                json_reader=self.json_reader,
                binary_reader=lambda _path: self.archive,
            )
        try:
            self.assertEqual(root.parent.resolve(), Path(tempfile.gettempdir()).resolve())
            self.assertEqual(root.stat().st_mode & 0o777, 0o700)
            self.assertEqual((root / "source-artifact.zip").stat().st_mode & 0o777, 0o600)
            self.assertEqual((root / "unsigned" / "packages.adb").read_bytes(), b"synthetic unsigned index\n")
            self.assertTrue((root / "unsigned" / "SOURCE_ARTIFACT.json").is_file())
        finally:
            self.cleanup_session(root)

    def make_session(self) -> Path:
        with self.pinned_digest():
            return lab.prepare_session(
                json_reader=self.json_reader,
                binary_reader=lambda _path: self.archive,
            )

    def make_key(self, parent: Path) -> Path:
        key_directory = tempfile.TemporaryDirectory(prefix="lab-sign-key-test-")
        self.addCleanup(key_directory.cleanup)
        key = Path(key_directory.name) / f"{parent.name}-synthetic-key.pem"
        key.write_bytes(b"synthetic test key; not used for cryptography\n")
        os.chmod(key, 0o600)
        return key

    def cleanup_session(self, root: Path) -> None:
        with self.pinned_digest():
            lab.cleanup_session(root, confirmation=f"DELETE {root.resolve()}")

    def test_sign_changes_only_index_and_writes_private_complete_manifest(self) -> None:
        root = self.make_session()
        key = self.make_key(root)
        calls: list[Path] = []

        def fake_sign(bundle: Path, mounted_key: Path) -> None:
            self.assertEqual(mounted_key, key.resolve())
            (bundle / "packages.adb").write_bytes(b"synthetic signed index\n")
            calls.append(bundle)

        try:
            with self.pinned_digest():
                signed = lab.sign_session(
                    root,
                    key,
                    confirmation=lab.CONFIRM_PHRASE,
                    json_reader=self.json_reader,
                    docker_runner=fake_sign,
                    tool_source_verifier=lambda: "c" * 40,
                )
            self.assertEqual(calls, [signed])
            self.assertEqual(signed.stat().st_mode & 0o777, 0o700)
            self.assertEqual((signed / "packages.adb").read_bytes(), b"synthetic signed index\n")
            self.assertEqual((signed / lab.PACKAGE_NAMES[0]).read_bytes(), b"synthetic core APK\n")
            self.assertEqual((signed / lab.PACKAGE_NAMES[1]).read_bytes(), b"synthetic LuCI APK\n")
            record = json.loads((signed / "LAB_SIGNING.json").read_text())
            self.assertEqual(record["signed_file"], "packages.adb")
            self.assertEqual(record["source"]["run_id"], lab.SOURCE_RUN_ID)
            self.assertEqual(record["tool_commit"], "c" * 40)
            entries = {path.name for path in signed.iterdir()}
            self.assertIn("BUILD_SHA256SUMS", entries)
            self.assertIn("SHA256SUMS", entries)
            self.assertNotIn("signing-key.pem", entries)
            for entry in signed.iterdir():
                self.assertFalse(entry.is_symlink())
                self.assertEqual(entry.stat().st_mode & 0o777, 0o600)
            for line in (signed / "SHA256SUMS").read_text().splitlines():
                digest, filename = line.split("  ", 1)
                self.assertEqual(sha256((signed / filename).read_bytes()), digest)
        finally:
            self.cleanup_session(root)

    def test_wrong_confirmation_never_starts_signer(self) -> None:
        root = self.make_session()
        key = self.make_key(root)
        calls: list[bool] = []
        try:
            with self.pinned_digest(), self.assertRaisesRegex(lab.LabSignError, "Confirmation"):
                lab.sign_session(
                    root,
                    key,
                    confirmation="yes",
                    json_reader=self.json_reader,
                    docker_runner=lambda *_: calls.append(True),
                    tool_source_verifier=lambda: "c" * 40,
                )
            self.assertEqual(calls, [])
            self.assertFalse((root / "signed-bundle").exists())
        finally:
            self.cleanup_session(root)

    def test_refuses_if_signer_changes_anything_except_index(self) -> None:
        root = self.make_session()
        key = self.make_key(root)

        def bad_sign(bundle: Path, _key: Path) -> None:
            (bundle / "packages.adb").write_bytes(b"changed index")
            (bundle / lab.PACKAGE_NAMES[0]).write_bytes(b"changed APK")

        try:
            with self.pinned_digest(), self.assertRaisesRegex(lab.LabSignError, "Artifact file changed"):
                lab.sign_session(
                    root,
                    key,
                    confirmation=lab.CONFIRM_PHRASE,
                    json_reader=self.json_reader,
                    docker_runner=bad_sign,
                    tool_source_verifier=lambda: "c" * 40,
                )
            self.assertFalse((root / "signed-bundle").exists())
        finally:
            self.cleanup_session(root)

    def test_signing_key_inside_session_is_rejected_and_cleanup_preserves_it(self) -> None:
        root = self.make_session()
        key = root / "unsigned" / "user-key.pem"
        key.write_bytes(b"synthetic user key; never read by test\n")
        os.chmod(key, 0o600)
        try:
            with self.assertRaisesRegex(lab.LabSignError, "outside the temporary lab-sign session"):
                lab.sign_session(
                    root,
                    key,
                    confirmation=lab.CONFIRM_PHRASE,
                    json_reader=self.json_reader,
                    docker_runner=lambda *_: self.fail("signer must not start"),
                    tool_source_verifier=lambda: "c" * 40,
                )
            with self.pinned_digest(), self.assertRaisesRegex(lab.LabSignError, "Unexpected file in unsigned"):
                lab.cleanup_session(root, confirmation=f"DELETE {root.resolve()}")
            self.assertTrue(key.is_file())
            self.assertTrue(root.is_dir())
        finally:
            key.unlink(missing_ok=True)
            self.cleanup_session(root)

    def test_signing_key_inside_repository_is_rejected_before_source_check(self) -> None:
        root = self.make_session()
        with tempfile.TemporaryDirectory(prefix="lab-sign-repository-key-test-") as directory:
            repository_root = Path(directory)
            ignored_directory = repository_root / ".local-ignored"
            ignored_directory.mkdir()
            key = ignored_directory / "ignored-private-key.pem"
            key.write_bytes(b"synthetic test key; not used for cryptography\n")
            os.chmod(key, 0o600)
            try:
                with (
                    mock.patch.object(lab, "ROOT", repository_root),
                    mock.patch.object(lab, "verify_live_source") as verify_source,
                    self.assertRaisesRegex(lab.LabSignError, "outside the repository"),
                ):
                    lab.sign_session(
                        root,
                        key,
                        confirmation=lab.CONFIRM_PHRASE,
                        json_reader=self.json_reader,
                        docker_runner=lambda *_: self.fail("signer must not start"),
                        tool_source_verifier=lambda: self.fail("tool verifier must not run"),
                    )
                verify_source.assert_not_called()
            finally:
                self.cleanup_session(root)

    def test_rejects_symlink_or_wrong_mode_signing_key(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            target = self.make_key(parent)
            symlink = parent / "key-link"
            symlink.symlink_to(target)
            with self.assertRaisesRegex(lab.LabSignError, "non-symlink"):
                lab._validate_private_key(symlink)
            os.chmod(target, 0o644)
            with self.assertRaisesRegex(lab.LabSignError, "mode 0600"):
                lab._validate_private_key(target)

    def test_sdk_invocation_is_pinned_offline_and_mounts_private_key_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            key = root / "key.pem"
            key.write_bytes(b"synthetic key")
            with mock.patch.object(lab.shutil, "which", return_value="/usr/bin/docker"):
                endpoint = json.dumps(
                    [{"Name": "desktop", "Endpoints": {"docker": {"Host": "unix:///tmp/docker.sock"}}}]
                )
                with mock.patch.object(
                    lab.subprocess,
                    "run",
                    side_effect=[
                        mock.Mock(returncode=0, stdout="desktop\n"),
                        mock.Mock(returncode=0, stdout=endpoint),
                        mock.Mock(returncode=0),
                    ],
                ) as run:
                    lab._run_sdk_sign(root / "bundle", key)
            command = run.call_args.args[0]
            self.assertEqual(command[1:4], ["--context", "desktop", "run"])
            self.assertIn("--network=none", command)
            self.assertIn("--read-only", command)
            self.assertIn(lab.SDK_IMAGE, command)
            self.assertIn(f"{key}:/signing-key.pem:ro", command)
            self.assertIn(f"{lab.PUBLIC_KEY_PATH}:/keys/{lab.PUBLIC_KEY_NAME}:ro", command)
            self.assertNotIn(f"{ROOT / 'keys'}:/keys:ro", command)
            self.assertIn("cd /promotion\nsha256sum -c /promotion/PACKAGE_SHA256SUMS", command[-1])
            self.assertEqual(command[-1].count("sha256sum -c /promotion/PACKAGE_SHA256SUMS"), 2)
            self.assertIn("APK_SIGN_ALLOW_UNTRUSTED=1 APK_BIN=/builder/staging_dir/host/bin/apk", command[-1])
            self.assertIn("/builder/staging_dir/host/bin/apk --keys-dir /keys verify", command[-1])

    def test_sign_script_requires_explicit_untrusted_input_opt_in(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            index = root / "packages.adb"
            index.write_bytes(b"synthetic index")
            key = root / "synthetic-key.pem"
            key.write_bytes(b"synthetic key")
            key.chmod(0o600)
            apk = root / "apk"
            apk.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n', encoding="utf-8")
            apk.chmod(0o700)
            env = dict(os.environ, APK_BIN=str(apk))
            env.pop("APK_SIGN_ALLOW_UNTRUSTED", None)
            command = ["sh", str(ROOT / "scripts/sign-apk-index.sh"), str(index), str(key)]
            default = subprocess.run(command, env=env, capture_output=True, text=True)
            self.assertEqual(default.returncode, 0, default.stderr)
            self.assertEqual(default.stdout.splitlines()[:2], ["adbsign", "--sign-key"])
            enabled = subprocess.run(
                command,
                env=dict(env, APK_SIGN_ALLOW_UNTRUSTED="1"),
                capture_output=True,
                text=True,
            )
            self.assertEqual(enabled.returncode, 0, enabled.stderr)
            self.assertEqual(
                enabled.stdout.splitlines()[:3],
                ["adbsign", "--allow-untrusted", "--sign-key"],
            )
            invalid = subprocess.run(
                command,
                env=dict(env, APK_SIGN_ALLOW_UNTRUSTED="yes"),
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(invalid.returncode, 0)
            self.assertIn("Invalid APK_SIGN_ALLOW_UNTRUSTED", invalid.stderr)

    def test_remote_docker_context_is_refused_before_signing_container(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            key = root / "key.pem"
            key.write_bytes(b"synthetic key")
            endpoint = json.dumps(
                [{"Name": "remote", "Endpoints": {"docker": {"Host": "ssh://builder.example"}}}]
            )
            with mock.patch.object(lab.shutil, "which", return_value="/usr/bin/docker"):
                with mock.patch.object(
                    lab.subprocess,
                    "run",
                    side_effect=[
                        mock.Mock(returncode=0, stdout="remote\n"),
                        mock.Mock(returncode=0, stdout=endpoint),
                    ],
                ) as run:
                    with self.assertRaisesRegex(lab.LabSignError, "remote Docker daemons are refused"):
                        lab._run_sdk_sign(root / "bundle", key)
            self.assertEqual(run.call_count, 2)

    def test_docker_environment_overrides_are_refused_before_context_inspection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            key = root / "key.pem"
            key.write_bytes(b"synthetic key")
            with mock.patch.object(lab.shutil, "which", return_value="/usr/bin/docker"):
                for variable, value in (
                    ("DOCKER_HOST", "tcp://builder.example:2376"),
                    ("DOCKER_CONTEXT", "remote"),
                ):
                    with self.subTest(variable=variable):
                        with mock.patch.dict(os.environ, {variable: value}):
                            with mock.patch.object(lab.subprocess, "run") as run:
                                with self.assertRaisesRegex(
                                    lab.LabSignError, "overrides are not allowed"
                                ):
                                    lab._run_sdk_sign(root / "bundle", key)
                        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
