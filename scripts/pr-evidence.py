#!/usr/bin/env python3
"""Create and enrich deterministic, secret-free PR evidence artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
CHECKSUM_LINE = re.compile(r"^([0-9a-f]{64})  (.+)$")
RESULTS = {"PASS", "FAIL", "SKIPPED"}
FINAL_RESULTS = {"READY_FOR_REVIEW", "BLOCKED", "FAILED"}


class EvidenceError(Exception):
    """Raised when evidence cannot be bound to a verified candidate."""


def _git(repo: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise EvidenceError("Git evidence could not be verified.") from exc
    return result.stdout.decode("utf-8", errors="surrogateescape").strip()


def _changed_files(repo: Path, base: str, candidate: str) -> list[str]:
    changed = subprocess.run(
        ["git", "-C", str(repo), "diff", "--name-only", "-z", "--no-renames", base, candidate],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    ).stdout
    return sorted(os.fsdecode(item) for item in changed.split(b"\0") if item)


def _atomic_json(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(
        document,
        ensure_ascii=True,
        indent=2,
        sort_keys=True,
    ) + "\n"
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary_name = stream.name
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    except OSError as exc:
        if temporary_name:
            try:
                os.unlink(temporary_name)
            except OSError:
                pass
        raise EvidenceError("Evidence JSON could not be written safely.") from exc


def _read_events(path: Path) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise EvidenceError("The private check-event log could not be read.") from exc
    for line in lines:
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise EvidenceError("The private check-event log is malformed.") from exc
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("name"), str)
            or not item["name"]
            or not isinstance(item.get("command"), str)
            or not item["command"]
            or not isinstance(item.get("result"), str)
            or item.get("result") not in RESULTS
            or not isinstance(item.get("blocking"), bool)
        ):
            raise EvidenceError("The private check-event log has an invalid entry.")
        if "exit_code" in item and (
            not isinstance(item["exit_code"], int) or isinstance(item["exit_code"], bool)
        ):
            raise EvidenceError("A recorded check has an invalid exit code.")
        if item["result"] == "PASS" and item.get("exit_code") != 0:
            raise EvidenceError("A passing check must have exit code zero.")
        if item["result"] == "FAIL" and item.get("exit_code") in (None, 0):
            raise EvidenceError("A failed check must have a nonzero exit code.")
        checks.append(item)
    return checks


def record(args: argparse.Namespace) -> None:
    if not args.name or not args.command:
        raise EvidenceError("A check name and command are required.")
    if args.result not in RESULTS:
        raise EvidenceError("Unsupported check result.")
    if args.result == "PASS" and args.exit_code != 0:
        raise EvidenceError("A passing check must have exit code zero.")
    if args.result == "FAIL" and (args.exit_code is None or args.exit_code == 0):
        raise EvidenceError("A failed check must have a nonzero exit code.")
    item: dict[str, Any] = {
        "blocking": args.blocking,
        "command": args.command,
        "name": args.name,
        "result": args.result,
    }
    if args.exit_code is not None:
        item["exit_code"] = args.exit_code
    if args.reason:
        item["reason"] = args.reason
    try:
        args.events.parent.mkdir(parents=True, exist_ok=True)
        with args.events.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(item, ensure_ascii=True, sort_keys=True) + "\n")
    except OSError as exc:
        raise EvidenceError("A private check-event could not be recorded.") from exc


def _manual_gates(args: argparse.Namespace) -> list[dict[str, Any]]:
    gates: list[dict[str, Any]] = []
    for name, state, owner in (
        ("openwrt_integration", args.openwrt, "Router & Release Validation"),
        ("ax4200_browser", args.browser, "Router & Release Validation"),
        ("release_execution", args.release, "Owner approval"),
        ("signing_security", args.signing, "PR Reviewer / protected environment"),
    ):
        if state not in {"required", "not_required", "owner_gated"}:
            raise EvidenceError("Unsupported manual-gate state.")
        gates.append(
            {
                "owner": owner,
                "performed": False,
                "status": state,
                "type": name,
            }
        )
    return gates


def _package_gates(repo: Path, changed_files: list[str]) -> list[dict[str, Any]]:
    """Read the existing bounded exact-path/tree filters, not a second mapping.

    This is not a general YAML/glob parser. Unsupported scheduling syntax is
    rejected so a workflow change cannot silently omit an applicable build.
    Applicability is not proof that GitHub scheduled or completed the build.
    """
    event = os.environ.get("GITHUB_EVENT_NAME", "pull_request")
    if event not in {"pull_request", "push"}:
        raise EvidenceError("Unsupported source-evidence scheduling event.")
    gates = []
    for workflow in ("build.yml", "build-24-10.yml"):
        text = (repo / ".github/workflows" / workflow).read_text(encoding="utf-8")
        block = re.search(
            rf"(?ms)^  {event}:\n(.*?)(?=^  [A-Za-z_]+:|^\S|\Z)", text
        )
        if not block or "    paths:\n" not in block[1]:
            raise EvidenceError("Package workflow path filters are unavailable.")
        lines = block[1].split("    paths:\n", 1)[1].splitlines()
        patterns = []
        for line in lines:
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            match = re.fullmatch(r'      - "([^"\n]+)"', line)
            if not match:
                raise EvidenceError("Unsupported package path-filter syntax.")
            pattern = match[1]
            plain = pattern[:-3] if pattern.endswith("/**") else pattern
            if not plain or any(char in plain for char in "*?![]{}\\"):
                raise EvidenceError("Unsupported package path-filter pattern.")
            patterns.append(pattern)
        if not patterns:
            raise EvidenceError("Package workflow path filters are empty.")
        required = any(
            path.startswith(pattern[:-2]) if pattern.endswith("/**") else path == pattern
            for path in changed_files for pattern in patterns
        )
        gates.append({"workflow": workflow, "status": "required" if required else "not_required",
                      "performed": False})
    return gates


def create(args: argparse.Namespace) -> None:
    if not FULL_SHA.fullmatch(args.base_sha) or not FULL_SHA.fullmatch(args.candidate_sha):
        raise EvidenceError("Base and candidate must be full lowercase commit SHAs.")
    if args.result not in FINAL_RESULTS:
        raise EvidenceError("Unsupported final evidence result.")

    repo = args.repo.resolve()
    if _git(repo, "rev-parse", "--show-toplevel") != str(repo):
        raise EvidenceError("Evidence must be generated from the repository root.")
    current_head = _git(repo, "rev-parse", "--verify", "HEAD")
    if current_head != args.candidate_sha:
        raise EvidenceError("The checkout HEAD is not the exact evidence candidate.")
    if _git(repo, "status", "--porcelain", "--untracked-files=all"):
        raise EvidenceError("The evidence checkout is not clean.")
    ancestor = subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", args.base_sha, args.candidate_sha],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if ancestor.returncode != 0:
        raise EvidenceError("Base is not an ancestor of the exact candidate.")
    changed_files = _changed_files(repo, args.base_sha, args.candidate_sha)
    if not changed_files:
        raise EvidenceError("The exact base/candidate diff is empty.")
    categories = sorted({value for value in args.categories.split(",") if value})
    checks = _read_events(args.events)
    gates = _manual_gates(args)
    failed = any(check["result"] == "FAIL" for check in checks)
    blocking_skips = any(
        check["result"] == "SKIPPED" and check["blocking"] for check in checks
    )
    required_gates = any(gate["status"] == "required" for gate in gates)
    if failed and args.result != "FAILED":
        raise EvidenceError("Failed checks require final result FAILED.")
    if not failed and args.result == "FAILED":
        raise EvidenceError("FAILED requires at least one recorded failed check.")
    if (blocking_skips or required_gates) and args.result == "READY_FOR_REVIEW":
        raise EvidenceError("Required manual evidence cannot be marked ready.")
    if not (blocking_skips or required_gates or failed) and args.result == "BLOCKED":
        raise EvidenceError("BLOCKED requires an outstanding gate or blocking skipped check.")

    document: dict[str, Any] = {
        "artifacts": [],
        "builds": [],
        "candidate": {
            "base_sha": args.base_sha,
            "candidate_sha": args.candidate_sha,
            "categories": categories,
            "changed_files": changed_files,
        },
        "checks": checks,
        "manual_gates": gates,
        "package_gates": _package_gates(repo, changed_files),
        "producer": {
            "command": [
                "sh",
                "scripts/check-pr.sh",
                args.base_sha,
                args.candidate_sha,
            ],
            "script": "scripts/check-pr.sh",
        },
        "result": args.result,
        "schema_version": SCHEMA_VERSION,
    }
    safe_ci = {}
    for env_name, field in (
        ("GITHUB_RUN_ID", "run_id"),
        ("GITHUB_RUN_ATTEMPT", "run_attempt"),
        ("GITHUB_WORKFLOW", "workflow"),
        ("GITHUB_EVENT_NAME", "event"),
    ):
        value = os.environ.get(env_name, "")
        if value and (field not in {"run_id", "run_attempt"} or value.isdigit()):
            safe_ci[field] = value
    if safe_ci:
        document["ci"] = safe_ci
    _atomic_json(args.output, document)


def verify_source(args: argparse.Namespace) -> None:
    """Validate freshly generated offline evidence; never clear manual/SDK gates."""
    if not FULL_SHA.fullmatch(args.base_sha) or not FULL_SHA.fullmatch(args.candidate_sha):
        raise EvidenceError("Expected identities must be full commit SHAs.")
    repo = args.repo.resolve()
    if (_git(repo, "rev-parse", "--show-toplevel") != str(repo)
            or _git(repo, "rev-parse", "HEAD") != args.candidate_sha
            or _git(repo, "status", "--porcelain", "--untracked-files=all")):
        raise EvidenceError("Source evidence requires the exact clean checkout.")
    _git(repo, "merge-base", "--is-ancestor", args.base_sha, args.candidate_sha)
    document = json.loads(args.evidence.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or type(document.get("schema_version")) is not int or document["schema_version"] != SCHEMA_VERSION:
        raise EvidenceError("Unsupported source evidence schema.")
    candidate = document.get("candidate")
    changed = _changed_files(repo, args.base_sha, args.candidate_sha)
    if (not isinstance(candidate, dict) or candidate.get("base_sha") != args.base_sha
            or candidate.get("candidate_sha") != args.candidate_sha or not changed
            or candidate.get("changed_files") != changed):
        raise EvidenceError("Source evidence does not match the exact base/head diff.")
    categories = candidate.get("categories")
    if (not isinstance(categories, list) or not categories
            or any(not isinstance(value, str) or not value for value in categories)
            or "unknown" in categories):
        raise EvidenceError("Unmapped or malformed source categories.")
    checks = document.get("checks")
    if not isinstance(checks, list) or not checks:
        raise EvidenceError("Source evidence lacks checks.")
    names = []
    for check in checks:
        if (not isinstance(check, dict) or not isinstance(check.get("name"), str)
                or not check["name"] or not isinstance(check.get("command"), str)
                or not check["command"] or type(check.get("blocking")) is not bool
                or check.get("result") not in ("PASS", "SKIPPED")
                or (check["result"] == "PASS" and (type(check.get("exit_code")) is not int or check["exit_code"] != 0))
                or (check["result"] == "SKIPPED" and
                    (check["blocking"] or check["name"] == "Full-validator LuCI JavaScript syntax"))):
            raise EvidenceError("Failed, incomplete or malformed offline checks.")
        names.append(check["name"])
    for required in ("Full repository validation", "Exact base/candidate whitespace check",
                     "Post-validation working-tree check", "Post-validation HEAD check"):
        if names.count(required) != 1 or next(check for check in checks if check["name"] == required)["result"] != "PASS":
            raise EvidenceError("A universal source check is missing or skipped.")
    gates = document.get("manual_gates")
    expected = {"openwrt_integration", "ax4200_browser", "release_execution", "signing_security"}
    if (not isinstance(gates, list) or len(gates) != len(expected)
            or any(not isinstance(gate, dict) or not isinstance(gate.get("type"), str)
                   or gate.get("status") not in ("required", "not_required", "owner_gated")
                   or gate.get("performed") is not False for gate in gates)
            or {gate["type"] for gate in gates} != expected):
        raise EvidenceError("Malformed or falsely completed manual gates.")
    required_manual = any(gate["status"] == "required" for gate in gates)
    if document.get("result") != ("BLOCKED" if required_manual else "READY_FOR_REVIEW"):
        raise EvidenceError("Source result contradicts outstanding manual gates.")
    package_gates = document.get("package_gates")
    if (not isinstance(package_gates, list)
            or any(not isinstance(gate, dict) or gate.get("performed") is not False
                   for gate in package_gates)
            or package_gates != _package_gates(repo, changed)):
        raise EvidenceError("Missing or inconsistent package-build requirements.")
    for env_name, field in (("GITHUB_RUN_ID", "run_id"), ("GITHUB_RUN_ATTEMPT", "run_attempt"),
                            ("GITHUB_WORKFLOW", "workflow"), ("GITHUB_EVENT_NAME", "event")):
        expected_ci = os.environ.get(env_name)
        if expected_ci and (not isinstance(document.get("ci"), dict)
                            or document["ci"].get(field) != expected_ci):
            raise EvidenceError("Source evidence belongs to a different CI run/event.")


def _checksum_manifest(path: Path, expected_files: set[str]) -> None:
    if path.is_symlink() or not path.is_file():
        raise EvidenceError("A required package checksum manifest is missing or unsafe.")
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise EvidenceError("A required package checksum manifest is missing.") from exc
    found: dict[str, str] = {}
    for line in lines:
        match = CHECKSUM_LINE.fullmatch(line)
        if not match:
            raise EvidenceError("A package checksum manifest has malformed data.")
        digest, name = match.groups()
        if name in found or Path(name).name != name:
            raise EvidenceError("A package checksum manifest has unsafe paths or duplicates.")
        found[name] = digest
    if set(found) != expected_files:
        raise EvidenceError("A package checksum manifest does not match the exact artifact files.")
    for name, expected in found.items():
        try:
            actual = hashlib.sha256((path.parent / name).read_bytes()).hexdigest()
        except OSError as exc:
            raise EvidenceError("A checksummed package artifact is missing.") from exc
        if actual != expected:
            raise EvidenceError("A package artifact checksum does not match its manifest.")


def attach_build(args: argparse.Namespace) -> None:
    try:
        document = json.loads(args.evidence.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceError("The source evidence JSON is unavailable or malformed.") from exc
    if not isinstance(document, dict) or document.get("schema_version") != SCHEMA_VERSION:
        raise EvidenceError("The source evidence schema is not supported.")
    if document.get("result") not in {"READY_FOR_REVIEW", "BLOCKED"}:
        raise EvidenceError("A failed or incomplete source evidence record cannot be built.")
    if not FULL_SHA.fullmatch(args.source_sha):
        raise EvidenceError("The build source must be a full lowercase commit SHA.")
    if not args.run_id.isdigit() or not args.workflow or not re.fullmatch(r"[^@\s]+@[0-9a-f]{40}", args.sdk_action):
        raise EvidenceError("The build run, workflow, or pinned SDK action is invalid.")
    repo = args.repo.resolve()
    if _git(repo, "rev-parse", "--verify", "HEAD") != args.source_sha:
        raise EvidenceError("The checked-out build source is not the exact evidence candidate.")
    candidate = document.get("candidate")
    if (
        not isinstance(candidate, dict)
        or not FULL_SHA.fullmatch(str(candidate.get("base_sha", "")))
        or candidate.get("candidate_sha") != args.source_sha
    ):
        raise EvidenceError("The package build is not bound to the evidence candidate.")
    if any(not isinstance(document.get(key), list) for key in ("checks", "artifacts", "builds")):
        raise EvidenceError("The source evidence has an invalid collection field.")
    if any(
        not isinstance(check, dict)
        or not isinstance(check.get("result"), str)
        or check.get("result") not in RESULTS
        or not isinstance(check.get("blocking"), bool)
        or not isinstance(check.get("name"), str)
        or not isinstance(check.get("command"), str)
        for check in document["checks"]
    ):
        raise EvidenceError("The source evidence contains a malformed check.")
    if any(
        check["result"] == "FAIL"
        or (check["result"] == "SKIPPED" and check["blocking"])
        for check in document["checks"]
    ):
        raise EvidenceError("Failed or blocking-skipped checks cannot be package-built.")
    gates = document.get("manual_gates")
    if not isinstance(gates, list) or any(
        not isinstance(gate, dict)
        or not isinstance(gate.get("status"), str)
        or gate.get("status") not in {"required", "not_required", "owner_gated"}
        or not isinstance(gate.get("performed"), bool)
        for gate in gates
    ):
        raise EvidenceError("The source evidence contains malformed manual gates.")
    if document.get("result") == "READY_FOR_REVIEW" and any(
        gate["status"] == "required" for gate in gates
    ):
        raise EvidenceError("Required manual gates cannot be marked ready for review.")
    if document.get("result") == "BLOCKED" and not (
        any(gate["status"] == "required" for gate in gates)
        or any(check["result"] == "SKIPPED" and check["blocking"] for check in document["checks"])
    ):
        raise EvidenceError("BLOCKED evidence must identify an outstanding required gate.")
    if any(
        not isinstance(item, dict)
        or not isinstance(item.get("name"), str)
        or not isinstance(item.get("package_format"), str)
        for item in document["artifacts"]
    ) or any(not isinstance(item, dict) for item in document["builds"]):
        raise EvidenceError("The source evidence contains malformed build artifacts.")
    if any(item.get("format") == args.format for item in document["builds"]):
        raise EvidenceError("This evidence already contains a build for the requested package format.")
    if args.format not in {"apk", "ipk"}:
        raise EvidenceError("Unsupported package format.")
    if args.artifact_dir.is_symlink():
        raise EvidenceError("The package artifact directory must not be a symlink.")
    artifact_dir = args.artifact_dir.resolve()
    try:
        source_commit = (artifact_dir / "SOURCE_COMMIT").read_text(encoding="utf-8").strip()
        release = (artifact_dir / "OPENWRT_RELEASE").read_text(encoding="utf-8").strip()
        architecture = (artifact_dir / "SDK_ARCH").read_text(encoding="utf-8").strip()
        package_format = (artifact_dir / "PACKAGE_FORMAT").read_text(encoding="utf-8").strip()
        names = (artifact_dir / "PACKAGES").read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise EvidenceError("The package artifact metadata is incomplete.") from exc
    for metadata_name in ("SOURCE_COMMIT", "OPENWRT_RELEASE", "SDK_ARCH", "PACKAGE_FORMAT", "PACKAGES"):
        metadata_path = artifact_dir / metadata_name
        if metadata_path.is_symlink() or not metadata_path.is_file():
            raise EvidenceError("Package artifact metadata must be regular files.")
    if source_commit != args.source_sha or package_format != args.format:
        raise EvidenceError("Package provenance does not match the exact candidate or format.")
    if release != args.release or architecture != args.architecture:
        raise EvidenceError("Package release or architecture does not match the build inputs.")
    if not names or len(names) != len(set(names)) or any(Path(name).name != name for name in names):
        raise EvidenceError("The package inventory is empty, duplicated, or unsafe.")
    suffix = f".{args.format}"
    if any(not name.endswith(suffix) for name in names):
        raise EvidenceError("The package inventory contains an unexpected file type.")
    package_files = set(names)
    if args.format == "apk":
        if len(names) != 2:
            raise EvidenceError("The APK evidence requires the exact two-package bundle.")
        _checksum_manifest(artifact_dir / "PACKAGE_SHA256SUMS", package_files)
        _checksum_manifest(artifact_dir / "SHA256SUMS", package_files | {"packages.adb"})
        artifact_files = sorted(package_files | {"packages.adb"})
    else:
        _checksum_manifest(artifact_dir / "SHA256SUMS", package_files)
        artifact_files = sorted(package_files)

    for filename in artifact_files:
        path = artifact_dir / filename
        if path.is_symlink() or not path.is_file():
            raise EvidenceError("A package artifact is not a regular file.")
        document["artifacts"].append(
            {
                "name": filename,
                "package_format": args.format,
                "purpose": "unsigned package build output",
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "size_bytes": path.stat().st_size,
            }
        )
    document["artifacts"] = sorted(document["artifacts"], key=lambda item: (item["package_format"], item["name"]))
    document["builds"].append(
        {
            "architecture": architecture,
            "format": args.format,
            "release": release,
            "source_sha": source_commit,
            "workflow": args.workflow,
            "run_id": args.run_id if args.run_id.isdigit() else "",
            "sdk_action": args.sdk_action,
            "sdk_inputs": {
                "ARCH": f"{architecture}-{release}",
                "BUILD_LOG": "1",
                "FEEDNAME": "xray_mitm",
                **({"INDEX": "1"} if args.format == "apk" else {}),
                "PACKAGES": "xray-mitm luci-app-xray-mitm",
                "V": "s",
            },
        }
    )
    document["builds"] = sorted(document["builds"], key=lambda item: (item["format"], item["release"], item["architecture"]))
    document["checks"].extend(
        [
            {
                "blocking": True,
                "command": args.sdk_action,
                "exit_code": 0,
                "inputs": {
                    "ARCH": f"{architecture}-{release}",
                    "BUILD_LOG": "1",
                    "FEEDNAME": "xray_mitm",
                    **({"INDEX": "1"} if args.format == "apk" else {}),
                    "PACKAGES": "xray-mitm luci-app-xray-mitm",
                    "V": "s",
                },
                "kind": "github_action",
                "name": "Official OpenWrt SDK package build",
                "result": "PASS",
            },
            {
                "blocking": True,
                "command": args.checksum_command,
                "exit_code": 0,
                "kind": "command",
                "name": "Package provenance and checksum verification",
                "result": "PASS",
            },
        ]
    )
    _atomic_json(args.evidence, document)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="operation", required=True)

    record_parser = commands.add_parser("record")
    record_parser.add_argument("--events", type=Path, required=True)
    record_parser.add_argument("--name", required=True)
    record_parser.add_argument("--command", required=True)
    record_parser.add_argument("--result", required=True, choices=sorted(RESULTS))
    record_parser.add_argument("--exit-code", type=int)
    record_parser.add_argument("--reason", default="")
    record_parser.add_argument("--blocking", action="store_true")
    record_parser.set_defaults(function=record)

    create_parser = commands.add_parser("create")
    create_parser.add_argument("--repo", type=Path, required=True)
    create_parser.add_argument("--output", type=Path, required=True)
    create_parser.add_argument("--events", type=Path, required=True)
    create_parser.add_argument("--base-sha", required=True)
    create_parser.add_argument("--candidate-sha", required=True)
    create_parser.add_argument("--categories", default="")
    create_parser.add_argument("--result", required=True, choices=sorted(FINAL_RESULTS))
    create_parser.add_argument("--openwrt", choices=("required", "not_required"), default="not_required")
    create_parser.add_argument("--browser", choices=("required", "not_required"), default="not_required")
    create_parser.add_argument("--release", choices=("owner_gated", "not_required"), default="not_required")
    create_parser.add_argument("--signing", choices=("owner_gated", "not_required"), default="not_required")
    create_parser.set_defaults(function=create)

    verify_parser = commands.add_parser("verify-source")
    verify_parser.add_argument("--repo", type=Path, required=True)
    verify_parser.add_argument("--evidence", type=Path, required=True)
    verify_parser.add_argument("--base-sha", required=True)
    verify_parser.add_argument("--candidate-sha", required=True)
    verify_parser.set_defaults(function=verify_source)

    build_parser = commands.add_parser("attach-build")
    build_parser.add_argument("--repo", type=Path, required=True)
    build_parser.add_argument("--evidence", type=Path, required=True)
    build_parser.add_argument("--artifact-dir", type=Path, required=True)
    build_parser.add_argument("--source-sha", required=True)
    build_parser.add_argument("--format", required=True, choices=("apk", "ipk"))
    build_parser.add_argument("--release", required=True)
    build_parser.add_argument("--architecture", required=True)
    build_parser.add_argument("--workflow", required=True)
    build_parser.add_argument("--run-id", required=True)
    build_parser.add_argument("--sdk-action", required=True)
    build_parser.add_argument("--checksum-command", required=True)
    build_parser.set_defaults(function=attach_build)
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        args.function(args)
    except EvidenceError as exc:
        print(f"PR_EVIDENCE_RESULT=FAILED\nERROR: {exc}", file=sys.stderr)
        return 1
    except (OSError, subprocess.CalledProcessError, ValueError) as exc:
        print("PR_EVIDENCE_RESULT=FAILED\nERROR: Evidence operation failed safely.", file=sys.stderr)
        return 1
    print("PR_EVIDENCE_RESULT=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
