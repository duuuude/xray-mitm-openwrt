#!/usr/bin/env python3
"""Prepare and locally sign the exact, already-built v0.4.5 APK artifact.

This tool never dispatches a workflow, builds packages, uploads artifacts, or
installs packages. Its source run and artifact are deliberately pinned.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Callable
from urllib.parse import urlsplit


REPOSITORY = "duuuude/xray-mitm-openwrt"
SOURCE_RUN_ID = 36903522011
SOURCE_WORKFLOW_ID = 351137159
SOURCE_COMMIT = "135bae3e54adb7d9181f79e08bd863bbf778fc8f"
SOURCE_ARTIFACT_ID = 11185431993
SOURCE_ARTIFACT_NAME = (
    "xray-mitm-openwrt-25.12.5-aarch64_generic-"
    "135bae3e54adb7d9181f79e08bd863bbf778fc8f"
)
SOURCE_ARTIFACT_DIGEST = (
    "sha256:902fcd2166b06bb695a01040415ef5632102b64d42f5a002cea87e9831152d9d"
)
OPENWRT_RELEASE = "25.12.5"
SDK_ARCH = "aarch64_generic"
SDK_IMAGE = (
    "ghcr.io/openwrt/sdk@sha256:"
    "d7759c08b2c0b0ffe57719bd8a293543708cbc27b18941478ebeae04c42986ed"
)
PUBLIC_KEY_NAME = "xray-mitm-feed-v1.pem"
PUBLIC_KEY_SHA256 = "3e0dc07ffef69d1512500b6add486381d8c261a8ec3fcce54fa403b35320df8a"
SESSION_PREFIX = "xray-mitm-lab-sign-v045-"
SESSION_VERSION = 1
MAX_ARCHIVE_BYTES = 8 * 1024 * 1024
MAX_UNPACKED_BYTES = 8 * 1024 * 1024
MAX_API_READ_CHUNK = 64 * 1024
CONFIRM_PHRASE = "SIGN ONLY packages.adb"

PACKAGE_NAMES = (
    "luci-app-xray-mitm-26.269.77380~a3bf576.apk",
    "xray-mitm-0.4.5-r1.apk",
)
SOURCE_PACKAGE_SHA256SUMS = (
    b"2ee473c8db32c62083c9945f2bb57aa1c93773833bcb2860e98153daff47bcdc  "
    b"luci-app-xray-mitm-26.269.77380~a3bf576.apk\n"
    b"a03f2758867ddc38eb6ace592b57bea300b4f58913f0dfb19497296a7de71f8d  "
    b"xray-mitm-0.4.5-r1.apk\n"
)
REQUIRED_ARTIFACT_FILES = frozenset(
    {
        "ARTIFACT_PURPOSE",
        "BUILD_EVENT",
        "BUILD_RUN_ID",
        "BUILD_WORKFLOW",
        "OPENWRT_RELEASE",
        "PACKAGE_FORMAT",
        "PACKAGES",
        "PACKAGE_SHA256SUMS",
        "SDK_ARCH",
        "SHA256SUMS",
        "SOURCE_COMMIT",
        "packages.adb",
        *PACKAGE_NAMES,
    }
)
KNOWN_UNSTAGED_FILES = frozenset(
    {"LICENSE", "README.fa.md", "README.md", "THIRD_PARTY_NOTICES.md", "install.sh"}
)
EXPECTED_ARCHIVE_FILES = REQUIRED_ARTIFACT_FILES | KNOWN_UNSTAGED_FILES
SESSION_ROOT_FILES = frozenset({"session.json", "source-artifact.zip"})
SESSION_ROOT_DIRS = frozenset({"unsigned", "signed-bundle"})
UNSIGNED_SESSION_FILES = REQUIRED_ARTIFACT_FILES | {"SOURCE_ARTIFACT.json"}
SIGNED_SESSION_FILES = REQUIRED_ARTIFACT_FILES | {
    "BUILD_SHA256SUMS",
    "LAB_SIGNING.json",
    PUBLIC_KEY_NAME,
}

ROOT = Path(__file__).resolve().parents[1]
VERIFY_SCRIPT = ROOT / "scripts/verify-promotion-artifact.sh"
SIGN_SCRIPT = ROOT / "scripts/sign-apk-index.sh"
PUBLIC_KEY_PATH = ROOT / "keys" / PUBLIC_KEY_NAME
CONTAINER_SIGN_COMMAND = """\
set -eu
umask 077
openssl pkey -in /signing-key.pem -pubout -out /tmp/derived-public.pem
openssl pkey -pubin -in /keys/xray-mitm-feed-v1.pem -outform DER -out /tmp/expected.der
openssl pkey -pubin -in /tmp/derived-public.pem -outform DER -out /tmp/derived.der
cmp -s /tmp/expected.der /tmp/derived.der
cd /promotion
sha256sum -c /promotion/PACKAGE_SHA256SUMS
APK_SIGN_ALLOW_UNTRUSTED=1 APK_BIN=/builder/staging_dir/host/bin/apk sh /sign-apk-index.sh /promotion/packages.adb /signing-key.pem
/builder/staging_dir/host/bin/apk --keys-dir /keys verify /promotion/packages.adb
sha256sum -c /promotion/PACKAGE_SHA256SUMS
"""


class LabSignError(Exception):
    """Expected fail-closed error shown without dumping command output."""


def _now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _gh_api(path: str, *, binary: bool = False) -> bytes:
    command = ["gh", "api", path]
    if binary:
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError as exc:
            raise LabSignError("GitHub CLI (gh) is required for source verification.") from exc
        if process.stdout is None:
            process.kill()
            process.wait()
            raise LabSignError("Could not stream the pinned source artifact safely.")
        output = bytearray()
        try:
            while len(output) <= MAX_ARCHIVE_BYTES:
                remaining = MAX_ARCHIVE_BYTES + 1 - len(output)
                chunk = process.stdout.read(min(MAX_API_READ_CHUNK, remaining))
                if not chunk:
                    break
                output.extend(chunk)
                if len(output) > MAX_ARCHIVE_BYTES:
                    process.kill()
                    process.wait()
                    raise LabSignError(
                        "Downloaded source artifact exceeds the safe archive size limit."
                    )
            returncode = process.wait()
        except OSError as exc:
            if process.poll() is None:
                process.kill()
                process.wait()
            raise LabSignError("Could not read the pinned source artifact safely.") from exc
        finally:
            process.stdout.close()
        if returncode != 0:
            raise LabSignError(
                f"GitHub API request failed for the pinned source endpoint (exit "
                f"{returncode}); no signing was attempted."
            )
        return bytes(output)

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise LabSignError("GitHub CLI (gh) is required for source verification.") from exc
    if result.returncode != 0:
        raise LabSignError(
            f"GitHub API request failed for the pinned source endpoint (exit "
            f"{result.returncode}); no signing was attempted."
        )
    if not binary:
        try:
            json.loads(result.stdout)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise LabSignError("GitHub returned invalid JSON for source verification.") from exc
    return result.stdout


def _gh_json(path: str) -> dict[str, Any]:
    try:
        payload = json.loads(_gh_api(path))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LabSignError("GitHub returned invalid JSON for source verification.") from exc
    if not isinstance(payload, dict):
        raise LabSignError("GitHub returned an unexpected source record.")
    return payload


def verify_run_record(run: dict[str, Any]) -> None:
    repository = run.get("repository")
    if not isinstance(repository, dict):
        repository = {}
    expected = {
        "id": SOURCE_RUN_ID,
        "workflow_id": SOURCE_WORKFLOW_ID,
        "status": "completed",
        "conclusion": "success",
        "event": "push",
        "run_attempt": 1,
        "head_branch": "main",
        "head_sha": SOURCE_COMMIT,
    }
    for field, value in expected.items():
        if run.get(field) != value:
            raise LabSignError(f"Pinned source run mismatch: {field}.")
    if repository.get("full_name") != REPOSITORY:
        raise LabSignError("Pinned source run belongs to a different repository.")


def verify_artifact_record(
    listing: dict[str, Any], run: dict[str, Any]
) -> dict[str, Any]:
    artifacts = listing.get("artifacts")
    if not isinstance(artifacts, list):
        raise LabSignError("GitHub returned an invalid artifact list.")
    matches = [
        item
        for item in artifacts
        if isinstance(item, dict) and item.get("id") == SOURCE_ARTIFACT_ID
    ]
    if len(matches) != 1:
        raise LabSignError("The exact pinned source artifact is missing or duplicated.")
    artifact = matches[0]
    if artifact.get("name") != SOURCE_ARTIFACT_NAME:
        raise LabSignError("Pinned source artifact name does not match.")
    if artifact.get("digest") != SOURCE_ARTIFACT_DIGEST:
        raise LabSignError("Pinned source artifact digest does not match.")
    if artifact.get("expired") is not False:
        raise LabSignError("The pinned source artifact is expired or its expiry is unknown.")
    size = artifact.get("size_in_bytes")
    if not isinstance(size, int) or size <= 0 or size > MAX_UNPACKED_BYTES:
        raise LabSignError("Pinned source artifact size is invalid or exceeds the safe limit.")
    workflow_run = artifact.get("workflow_run")
    if not isinstance(workflow_run, dict):
        raise LabSignError("Pinned artifact is not bound to a workflow run.")
    bound_fields = {
        "id": SOURCE_RUN_ID,
        "head_branch": "main",
        "head_sha": SOURCE_COMMIT,
    }
    for field, value in bound_fields.items():
        if workflow_run.get(field) != value:
            raise LabSignError(f"Pinned artifact run binding mismatch: {field}.")
    if run.get("id") != workflow_run.get("id"):
        raise LabSignError("Pinned artifact is not bound to the verified source run.")
    return artifact


def verify_live_source(
    json_reader: Callable[[str], dict[str, Any]] = _gh_json,
) -> tuple[dict[str, Any], dict[str, Any]]:
    run_path = f"repos/{REPOSITORY}/actions/runs/{SOURCE_RUN_ID}"
    artifact_path = (
        f"repos/{REPOSITORY}/actions/runs/{SOURCE_RUN_ID}/artifacts?per_page=100"
    )
    run = json_reader(run_path)
    verify_run_record(run)
    listing = json_reader(artifact_path)
    artifact = verify_artifact_record(listing, run)
    return run, artifact


def verify_tool_source(
    json_reader: Callable[[str], dict[str, Any]] = _gh_json,
    *,
    root: Path = ROOT,
    tracked_paths: tuple[str, ...] = (
        "scripts/lab_sign_v045.py",
        "scripts/sign-apk-index.sh",
        "scripts/verify-promotion-artifact.sh",
        f"keys/{PUBLIC_KEY_NAME}",
    ),
) -> str:
    try:
        top = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
        )
        branch = subprocess.run(
            ["git", "-C", str(root), "branch", "--show-current"],
            capture_output=True,
            text=True,
            check=False,
        )
        head = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--verify", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        status = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise LabSignError("Git is required to verify the local signer source.") from exc
    if any(result.returncode != 0 for result in (top, branch, head, status)):
        raise LabSignError("Could not verify the local signer checkout; signing is blocked.")
    checkout = Path(top.stdout.strip()).resolve()
    if checkout != root.resolve() or branch.stdout.strip() != "main":
        raise LabSignError("Signing is allowed only from the repository's main checkout.")
    if status.stdout:
        raise LabSignError("The signer checkout is dirty; signing is blocked.")
    local_head = head.stdout.strip()
    if len(local_head) != 40 or any(char not in "0123456789abcdef" for char in local_head):
        raise LabSignError("The local signer HEAD is not a full commit SHA.")
    for relative in tracked_paths:
        path = root / relative
        try:
            item = path.lstat()
        except OSError as exc:
            raise LabSignError(f"A required signer source file is unavailable: {relative}.") from exc
        if stat.S_ISLNK(item.st_mode) or not stat.S_ISREG(item.st_mode):
            raise LabSignError(f"A required signer source file is not a regular file: {relative}.")
        try:
            committed = subprocess.run(
                ["git", "-C", str(root), "rev-parse", "--verify", f"HEAD:{relative}"],
                capture_output=True,
                text=True,
                check=False,
            )
            working = subprocess.run(
                ["git", "-C", str(root), "hash-object", "--", str(path)],
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as exc:
            raise LabSignError("Could not verify tracked signer source files.") from exc
        if committed.returncode != 0 or working.returncode != 0:
            raise LabSignError(f"A required signer source file is not committed: {relative}.")
        if committed.stdout.strip() != working.stdout.strip():
            raise LabSignError(f"A required signer source file differs from live main: {relative}.")
    live_main = json_reader(f"repos/{REPOSITORY}/commits/main")
    if live_main.get("sha") != local_head:
        raise LabSignError("Local signer HEAD does not exactly match live GitHub main.")
    return local_head


def _read_archive(archive_bytes: bytes) -> dict[str, bytes]:
    if not archive_bytes or len(archive_bytes) > MAX_ARCHIVE_BYTES:
        raise LabSignError("Source artifact archive is empty or exceeds the safe size limit.")
    actual_digest = "sha256:" + _sha256(archive_bytes)
    if actual_digest != SOURCE_ARTIFACT_DIGEST:
        raise LabSignError("Downloaded source archive digest does not match GitHub metadata.")
    try:
        archive = zipfile.ZipFile(io.BytesIO(archive_bytes))
        infos = archive.infolist()
    except (OSError, zipfile.BadZipFile) as exc:
        raise LabSignError("Downloaded source artifact is not a valid ZIP archive.") from exc
    if not infos or len(infos) > 32:
        raise LabSignError("Source artifact contains an invalid number of entries.")
    names: list[str] = []
    total_unpacked = 0
    for info in infos:
        name = info.filename
        path = PurePosixPath(name)
        mode = (info.external_attr >> 16) & 0xFFFF
        file_type = stat.S_IFMT(mode)
        if (
            not name
            or "\\" in name
            or "/" in name
            or path.is_absolute()
            or len(path.parts) != 1
            or name in {".", ".."}
            or info.is_dir()
            or info.flag_bits & 0x1
            or (file_type not in {0, stat.S_IFREG})
            or stat.S_ISLNK(mode)
        ):
            raise LabSignError("Source artifact contains an unsafe ZIP entry.")
        names.append(name)
        total_unpacked += info.file_size
        if info.file_size < 0 or total_unpacked > MAX_UNPACKED_BYTES:
            raise LabSignError("Source artifact expands beyond the safe size limit.")
    if len(names) != len(set(names)):
        raise LabSignError("Source artifact contains duplicate ZIP entries.")
    if set(names) != EXPECTED_ARCHIVE_FILES:
        raise LabSignError("Source artifact file list differs from the reviewed exact bundle.")
    files: dict[str, bytes] = {}
    try:
        for name in REQUIRED_ARTIFACT_FILES:
            files[name] = archive.read(name)
    except (KeyError, OSError, zipfile.BadZipFile, RuntimeError) as exc:
        raise LabSignError("A required source artifact entry could not be read.") from exc
    _verify_source_payload(files)
    return files


def _text(files: dict[str, bytes], name: str) -> str:
    try:
        return files[name].decode("utf-8").strip()
    except (KeyError, UnicodeDecodeError) as exc:
        raise LabSignError(f"Source artifact metadata is invalid: {name}.") from exc


def _verify_source_payload(files: dict[str, bytes]) -> None:
    exact_metadata = {
        "SOURCE_COMMIT": SOURCE_COMMIT,
        "OPENWRT_RELEASE": OPENWRT_RELEASE,
        "SDK_ARCH": SDK_ARCH,
        "PACKAGE_FORMAT": "apk",
        "ARTIFACT_PURPOSE": "promotable unsigned APK bundle",
        "BUILD_RUN_ID": str(SOURCE_RUN_ID),
        "BUILD_WORKFLOW": "Build OpenWrt APKs",
        "BUILD_EVENT": "push",
    }
    for name, expected in exact_metadata.items():
        if _text(files, name) != expected:
            raise LabSignError(f"Source artifact metadata mismatch: {name}.")
    package_list = _text(files, "PACKAGES").splitlines()
    if len(package_list) != len(PACKAGE_NAMES) or set(package_list) != set(PACKAGE_NAMES):
        raise LabSignError("Source artifact package list does not match the exact candidate.")
    if files.get("PACKAGE_SHA256SUMS") != SOURCE_PACKAGE_SHA256SUMS:
        raise LabSignError("Source artifact package checksums do not match the exact candidate.")


def _write_private_file(path: Path, data: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
    os.chmod(path, 0o600)


def _json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _source_record(run: dict[str, Any], artifact: dict[str, Any]) -> dict[str, Any]:
    return {
        "repository": REPOSITORY,
        "workflow_id": SOURCE_WORKFLOW_ID,
        "run_id": SOURCE_RUN_ID,
        "run_attempt": 1,
        "event": "push",
        "branch": "main",
        "source_commit": SOURCE_COMMIT,
        "artifact_id": SOURCE_ARTIFACT_ID,
        "artifact_name": SOURCE_ARTIFACT_NAME,
        "artifact_digest": SOURCE_ARTIFACT_DIGEST,
        "artifact_size_in_bytes": artifact["size_in_bytes"],
        "openwrt_release": OPENWRT_RELEASE,
        "sdk_arch": SDK_ARCH,
        "package_names": list(PACKAGE_NAMES),
        "verified_at_utc": _now_utc(),
    }


def _verify_promotion_artifact(directory: Path) -> None:
    try:
        result = subprocess.run(
            [
                "sh",
                str(VERIFY_SCRIPT),
                str(directory),
                SOURCE_COMMIT,
                OPENWRT_RELEASE,
                SDK_ARCH,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise LabSignError("Could not run the existing promotion-artifact verifier.") from exc
    if result.returncode != 0:
        raise LabSignError(
            "Exact APK package metadata or checksum verification failed; "
            "the artifact was not signed."
        )


def prepare_session(
    *,
    json_reader: Callable[[str], dict[str, Any]] = _gh_json,
    binary_reader: Callable[[str], bytes] | None = None,
    temp_parent: Path | None = None,
) -> Path:
    run, artifact = verify_live_source(json_reader)
    if binary_reader is None:
        binary_reader = lambda path: _gh_api(path, binary=True)
    download_path = (
        f"repos/{REPOSITORY}/actions/artifacts/{SOURCE_ARTIFACT_ID}/zip"
    )
    archive_bytes = binary_reader(download_path)
    files = _read_archive(archive_bytes)
    parent = temp_parent or Path(tempfile.gettempdir())
    root = Path(tempfile.mkdtemp(prefix=SESSION_PREFIX, dir=parent))
    os.chmod(root, 0o700)
    try:
        unsigned = root / "unsigned"
        unsigned.mkdir(mode=0o700)
        _write_private_file(root / "source-artifact.zip", archive_bytes)
        source = _source_record(run, artifact)
        session = {
            "session_version": SESSION_VERSION,
            "created_at_utc": _now_utc(),
            "source": source,
        }
        _write_private_file(root / "session.json", _json_bytes(session))
        _write_private_file(unsigned / "SOURCE_ARTIFACT.json", _json_bytes(source))
        for name, data in files.items():
            _write_private_file(unsigned / name, data)
        _verify_promotion_artifact(unsigned)
    except Exception:
        _remove_generated_session_tree(root)
        raise
    return root


def _validate_session_tree(root: Path, *, require_complete: bool) -> None:
    allowed_root = SESSION_ROOT_FILES | SESSION_ROOT_DIRS
    required_root = SESSION_ROOT_FILES | {"unsigned"}
    try:
        root_entries = {entry.name: entry for entry in root.iterdir()}
    except OSError as exc:
        raise LabSignError("Could not safely inspect the lab-sign session contents.") from exc
    unexpected = set(root_entries) - allowed_root
    if unexpected:
        raise LabSignError(
            "Unexpected session entry; refusing to remove or overwrite user data."
        )
    if require_complete and not required_root.issubset(root_entries):
        raise LabSignError("Lab-sign session is incomplete; cleanup is blocked.")
    for name in SESSION_ROOT_FILES & set(root_entries):
        item = root_entries[name].lstat()
        if stat.S_ISLNK(item.st_mode) or not stat.S_ISREG(item.st_mode):
            raise LabSignError(f"Session entry is not a regular file: {name}.")

    for directory_name, allowed_files, required_files in (
        ("unsigned", UNSIGNED_SESSION_FILES, UNSIGNED_SESSION_FILES),
        ("signed-bundle", SIGNED_SESSION_FILES, frozenset()),
    ):
        entry = root_entries.get(directory_name)
        if entry is None:
            if require_complete and directory_name == "unsigned":
                raise LabSignError("Lab-sign session is missing its unsigned bundle.")
            continue
        directory_stat = entry.lstat()
        if stat.S_ISLNK(directory_stat.st_mode) or not stat.S_ISDIR(directory_stat.st_mode):
            raise LabSignError(f"Session entry is not a real directory: {directory_name}.")
        if stat.S_IMODE(directory_stat.st_mode) & 0o077:
            raise LabSignError(f"Session directory is not private: {directory_name}.")
        try:
            entries = {child.name: child for child in entry.iterdir()}
        except OSError as exc:
            raise LabSignError(f"Could not safely inspect {directory_name}.") from exc
        if set(entries) - allowed_files:
            raise LabSignError(
                f"Unexpected file in {directory_name}; refusing to remove or overwrite user data."
            )
        if require_complete and not required_files.issubset(entries):
            raise LabSignError(f"Lab-sign session {directory_name} is incomplete.")
        for filename, child in entries.items():
            item = child.lstat()
            if stat.S_ISLNK(item.st_mode) or not stat.S_ISREG(item.st_mode):
                raise LabSignError(
                    f"Session entry is not a regular file: {directory_name}/{filename}."
                )


def _remove_generated_session_tree(root: Path) -> None:
    _validate_session_tree(root, require_complete=False)
    shutil.rmtree(root)


def _session_root(path: Path) -> tuple[Path, dict[str, Any]]:
    try:
        raw = path.lstat()
    except OSError as exc:
        raise LabSignError("Lab-sign session directory is unavailable.") from exc
    if stat.S_ISLNK(raw.st_mode) or not stat.S_ISDIR(raw.st_mode):
        raise LabSignError("Lab-sign session path must be a real directory, not a symlink.")
    root = path.resolve()
    expected_parent = Path(tempfile.gettempdir()).resolve()
    if root.parent.resolve() != expected_parent or not root.name.startswith(SESSION_PREFIX):
        raise LabSignError("Lab-sign session must remain in its private temporary directory.")
    if stat.S_IMODE(root.stat().st_mode) & 0o077:
        raise LabSignError("Lab-sign session directory is not private (expected mode 0700).")
    _validate_session_tree(root, require_complete=False)
    try:
        session = json.loads((root / "session.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LabSignError("Lab-sign session manifest is missing or invalid.") from exc
    if not isinstance(session, dict) or session.get("session_version") != SESSION_VERSION:
        raise LabSignError("Lab-sign session manifest version is unsupported.")
    source = session.get("source")
    if not isinstance(source, dict):
        raise LabSignError("Lab-sign session source identity is missing.")
    expected = {
        "repository": REPOSITORY,
        "workflow_id": SOURCE_WORKFLOW_ID,
        "run_id": SOURCE_RUN_ID,
        "run_attempt": 1,
        "event": "push",
        "branch": "main",
        "source_commit": SOURCE_COMMIT,
        "artifact_id": SOURCE_ARTIFACT_ID,
        "artifact_name": SOURCE_ARTIFACT_NAME,
        "artifact_digest": SOURCE_ARTIFACT_DIGEST,
        "openwrt_release": OPENWRT_RELEASE,
        "sdk_arch": SDK_ARCH,
        "package_names": list(PACKAGE_NAMES),
    }
    for field, value in expected.items():
        if source.get(field) != value:
            raise LabSignError(f"Lab-sign session identity mismatch: {field}.")
    _validate_session_tree(root, require_complete=True)
    return root, session


def _validate_private_key(path: Path) -> Path:
    try:
        item = path.lstat()
    except OSError as exc:
        raise LabSignError("Signing-key file is unavailable.") from exc
    if stat.S_ISLNK(item.st_mode) or not stat.S_ISREG(item.st_mode):
        raise LabSignError("Signing key must be a regular, non-symlink file.")
    if stat.S_IMODE(item.st_mode) != 0o600:
        raise LabSignError("Signing key must have file mode 0600.")
    if hasattr(os, "getuid") and item.st_uid != os.getuid():
        raise LabSignError("Signing key must be owned by the current user.")
    return path.resolve()


def _read_pinned_public_key() -> bytes:
    try:
        item = PUBLIC_KEY_PATH.lstat()
        if stat.S_ISLNK(item.st_mode) or not stat.S_ISREG(item.st_mode):
            raise LabSignError("Repository feed public key must be a regular non-symlink file.")
        data = PUBLIC_KEY_PATH.read_bytes()
    except OSError as exc:
        raise LabSignError("Repository feed public key is unavailable.") from exc
    if _sha256(data) != PUBLIC_KEY_SHA256:
        raise LabSignError("Repository feed public-key fingerprint does not match the installed trust anchor.")
    return data


def _write_checksum_manifest(directory: Path, filenames: list[str]) -> bytes:
    lines = []
    for name in sorted(filenames):
        path = directory / name
        if path.is_symlink() or not path.is_file():
            raise LabSignError("Signed bundle contains a non-regular file.")
        lines.append(f"{_sha256(path.read_bytes())}  {name}")
    content = ("\n".join(lines) + "\n").encode("ascii")
    _write_private_file(directory / "SHA256SUMS", content)
    return content


def _run_sdk_sign(bundle: Path, key_path: Path) -> None:
    docker = shutil.which("docker")
    if docker is None:
        raise LabSignError("Docker is required to use the pinned OpenWrt signing tools.")
    if "DOCKER_HOST" in os.environ or "DOCKER_CONTEXT" in os.environ:
        raise LabSignError(
            "Docker host/context overrides are not allowed; unset DOCKER_HOST and DOCKER_CONTEXT."
        )
    try:
        context = subprocess.run(
            [docker, "context", "show"], capture_output=True, text=True, check=False
        )
        if context.returncode != 0 or not context.stdout.strip():
            raise LabSignError("Could not verify the selected Docker context; signing is blocked.")
        inspected = subprocess.run(
            [docker, "context", "inspect", context.stdout.strip()],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise LabSignError("Could not inspect the Docker endpoint; signing is blocked.") from exc
    if inspected.returncode != 0:
        raise LabSignError("Could not inspect the selected Docker endpoint; signing is blocked.")
    try:
        contexts = json.loads(inspected.stdout)
        endpoint = contexts[0]["Endpoints"]["docker"]["Host"]
        inspected_name = contexts[0]["Name"]
    except (IndexError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise LabSignError("Docker returned an invalid context endpoint; signing is blocked.") from exc
    try:
        parsed_endpoint = urlsplit(endpoint) if isinstance(endpoint, str) else None
    except ValueError as exc:
        raise LabSignError("Docker returned an invalid context endpoint; signing is blocked.") from exc
    if (
        len(contexts) != 1
        or inspected_name != context.stdout.strip()
        or parsed_endpoint is None
        or parsed_endpoint.scheme != "unix"
        or parsed_endpoint.netloc
        or not parsed_endpoint.path.startswith("/")
    ):
        raise LabSignError(
            "Signing requires a local Unix-socket Docker endpoint; remote Docker daemons are refused."
        )
    command = [
        docker,
        "--context",
        context.stdout.strip(),
        "run",
        "--rm",
        "--network=none",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,noexec,size=16m",
        "-v",
        f"{bundle}:/promotion:rw",
        "-v",
        f"{key_path}:/signing-key.pem:ro",
        "-v",
        f"{PUBLIC_KEY_PATH}:/keys/{PUBLIC_KEY_NAME}:ro",
        "-v",
        f"{SIGN_SCRIPT}:/sign-apk-index.sh:ro",
        "--entrypoint",
        "/bin/sh",
        SDK_IMAGE,
        "-ceu",
        CONTAINER_SIGN_COMMAND,
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
    except OSError as exc:
        raise LabSignError("Could not start the pinned OpenWrt SDK signing container.") from exc
    if result.returncode != 0:
        raise LabSignError(
            "Pinned SDK signing/key-match/index-verification failed "
            f"(exit {result.returncode}); inspect the local tool output before retrying."
        )


def sign_session(
    session_path: Path,
    key_path: Path,
    *,
    confirmation: str | None = None,
    json_reader: Callable[[str], dict[str, Any]] = _gh_json,
    docker_runner: Callable[[Path, Path], None] = _run_sdk_sign,
    tool_source_verifier: Callable[[], str] | None = None,
) -> Path:
    key = _validate_private_key(key_path)
    candidate_root = session_path.resolve()
    if key == candidate_root or candidate_root in key.parents:
        raise LabSignError("Signing key must be outside the temporary lab-sign session.")
    repository_root = ROOT.resolve()
    if key == repository_root or repository_root in key.parents:
        raise LabSignError("Signing key must be outside the repository.")
    root, session = _session_root(session_path)
    verify_live_source(json_reader)
    archive_path = root / "source-artifact.zip"
    try:
        archive_bytes = archive_path.read_bytes()
    except OSError as exc:
        raise LabSignError("The verified source archive is missing.") from exc
    if "sha256:" + _sha256(archive_bytes) != SOURCE_ARTIFACT_DIGEST:
        raise LabSignError("Saved source archive digest changed; signing is blocked.")
    source_files = _read_archive(archive_bytes)
    if tool_source_verifier is None:
        tool_source_verifier = lambda: verify_tool_source(json_reader)
    tool_commit = tool_source_verifier()
    if confirmation is None:
        print(
            f"Exact source run {SOURCE_RUN_ID}, commit {SOURCE_COMMIT}; "
            f"artifact {SOURCE_ARTIFACT_ID}."
        )
        print("Only packages.adb will be signed; the APK files are hash-checked before and after.")
        print("The signing container has no network and mounts the local key read-only.")
        confirmation = input(f"Type {CONFIRM_PHRASE} to authorize local signing: ")
    if confirmation != CONFIRM_PHRASE:
        raise LabSignError("Confirmation did not match; no signing container was started.")

    signed = root / "signed-bundle"
    try:
        signed.mkdir(mode=0o700)
    except FileExistsError as exc:
        raise LabSignError("A signed-bundle directory already exists; refusing to overwrite it.") from exc
    try:
        for name, data in source_files.items():
            _write_private_file(signed / name, data)
        original_sha256sums = (signed / "SHA256SUMS").read_bytes()
        _write_private_file(signed / "BUILD_SHA256SUMS", original_sha256sums)
        public_key = _read_pinned_public_key()
        _write_private_file(signed / PUBLIC_KEY_NAME, public_key)
        _verify_promotion_artifact(signed)
        original_apk_hashes = {name: _sha256(source_files[name]) for name in PACKAGE_NAMES}
        original_file_hashes = {
            name: _sha256(data) for name, data in source_files.items()
        }
        docker_runner(signed, key)

        if tool_source_verifier() != tool_commit:
            raise LabSignError("The verified main signer source changed during signing; output is rejected.")

        if _sha256(_read_pinned_public_key()) != PUBLIC_KEY_SHA256:
            raise LabSignError("Repository public key changed during signing; output is rejected.")

        if _sha256((signed / "packages.adb").read_bytes()) == original_file_hashes["packages.adb"]:
            raise LabSignError("APK index did not change after signing; output is not signed.")
        for name, expected_hash in original_file_hashes.items():
            if name == "packages.adb":
                continue
            if _sha256((signed / name).read_bytes()) != expected_hash:
                raise LabSignError(f"Artifact file changed during signing: {name}.")
        for name, expected_hash in original_apk_hashes.items():
            if _sha256((signed / name).read_bytes()) != expected_hash:
                raise LabSignError(f"APK bytes changed during signing: {name}.")
        _verify_package_checksum_file(signed)
        expected_files = set(source_files) | {
            "BUILD_SHA256SUMS",
            "LAB_SIGNING.json",
            PUBLIC_KEY_NAME,
        }
        signing_record = {
            "method": "local pinned OpenWrt SDK container",
            "tool_commit": tool_commit,
            "sdk_image": SDK_IMAGE,
            "signed_file": "packages.adb",
            "source": session["source"],
            "signed_index_sha256": _sha256((signed / "packages.adb").read_bytes()),
            "public_key_sha256": _sha256(public_key),
            "apk_sha256": original_apk_hashes,
            "created_at_utc": _now_utc(),
            "recommended_retention_hours": 24,
        }
        _write_private_file(signed / "LAB_SIGNING.json", _json_bytes(signing_record))
        expected_files.discard("SHA256SUMS")
        (signed / "SHA256SUMS").unlink()
        _write_checksum_manifest(signed, sorted(expected_files))
        actual_files = {entry.name for entry in signed.iterdir()}
        if actual_files != expected_files | {"SHA256SUMS"}:
            raise LabSignError("Signed bundle contains missing or unexpected files.")
        for entry in signed.iterdir():
            if entry.is_symlink() or not entry.is_file():
                raise LabSignError("Signed bundle contains a non-regular file.")
            os.chmod(entry, 0o600)
        os.chmod(signed, 0o700)
    except Exception:
        try:
            _remove_known_directory(signed, SIGNED_SESSION_FILES)
        except LabSignError as cleanup_error:
            raise LabSignError(
                "Signing failed and unexpected files were found; the signed bundle was left untouched."
            ) from cleanup_error
        raise
    return signed


def _verify_package_checksum_file(directory: Path) -> None:
    manifest = directory / "PACKAGE_SHA256SUMS"
    try:
        lines = manifest.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise LabSignError("APK checksum manifest is missing or invalid.") from exc
    parsed: dict[str, str] = {}
    for line in lines:
        parts = line.split("  ", 1)
        if len(parts) != 2 or len(parts[0]) != 64 or parts[1] in parsed:
            raise LabSignError("APK checksum manifest is malformed.")
        parsed[parts[1]] = parts[0]
    if set(parsed) != set(PACKAGE_NAMES):
        raise LabSignError("APK checksum manifest does not exactly describe the packages.")
    for name, expected in parsed.items():
        if _sha256((directory / name).read_bytes()) != expected:
            raise LabSignError(f"APK checksum changed during signing: {name}.")


def cleanup_session(
    session_path: Path, *, confirmation: str | None = None
) -> None:
    root, _ = _session_root(session_path)
    exact_confirmation = f"DELETE {root}"
    if confirmation is None:
        print("This removes only the verified local lab-sign session directory.")
        confirmation = input(f"Type {exact_confirmation} to delete it: ")
    if confirmation != exact_confirmation:
        raise LabSignError("Confirmation did not match; local files were left untouched.")
    _validate_session_tree(root, require_complete=True)
    shutil.rmtree(root)


def _remove_known_directory(directory: Path, allowed_files: frozenset[str]) -> None:
    try:
        item = directory.lstat()
        entries = {entry.name: entry for entry in directory.iterdir()}
    except FileNotFoundError:
        return
    except OSError as exc:
        raise LabSignError("Could not safely inspect generated signing output.") from exc
    if stat.S_ISLNK(item.st_mode) or not stat.S_ISDIR(item.st_mode):
        raise LabSignError("Generated signing output is not a real directory.")
    if set(entries) - allowed_files:
        raise LabSignError("Unexpected files in generated signing output.")
    for name, entry in entries.items():
        child = entry.lstat()
        if stat.S_ISLNK(child.st_mode) or not stat.S_ISREG(child.st_mode):
            raise LabSignError(f"Unexpected non-file in generated signing output: {name}.")
    shutil.rmtree(directory)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("prepare", help="verify and privately stage the pinned unsigned APK artifact")
    sign_parser = subparsers.add_parser("sign", help="explicitly sign only packages.adb locally")
    sign_parser.add_argument("--session-dir", required=True, type=Path)
    sign_parser.add_argument("--key", required=True, type=Path)
    cleanup_parser = subparsers.add_parser("cleanup", help="remove one verified local staging/signing session")
    cleanup_parser.add_argument("--session-dir", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "prepare":
            root = prepare_session()
            print("Exact pinned APK artifact verified; no signing occurred.")
            print(f"Private temporary session: {root}")
            print(f"Prepared unsigned input: {root / 'unsigned'}")
            print("No build, upload, router transfer, or installation was performed.")
        elif args.command == "sign":
            output = sign_session(args.session_dir, args.key)
            print(f"Verified local signed bundle: {output}")
            print("Only packages.adb was signed; APK hashes and the signed index were verified.")
            print("No upload, router transfer, installation, or publication was performed.")
            print("Clean this temporary session within 24 hours when lab checks are complete.")
        elif args.command == "cleanup":
            cleanup_session(args.session_dir)
            print("Verified local lab-sign session removed.")
        return 0
    except (LabSignError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
