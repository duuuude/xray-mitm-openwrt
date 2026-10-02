#!/usr/bin/env python3
"""Write and verify durable, local-only Work report handoff artifacts."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import secrets
import stat
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator


SCHEMA = "xray-mitm-work-report/v1"
ACK_SCHEMA = "xray-mitm-work-report-ack/v1"
TASK_ID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
REPORT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
MAX_REPORT_BYTES = 1024 * 1024
MAX_ARTIFACT_BYTES = 2 * 1024 * 1024
DIRECTORY_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)


class HandoffError(Exception):
    """Raised when a durable handoff cannot be trusted."""


def _assert_repo_path(repo: Path, repo_fd: int) -> None:
    try:
        path_metadata = repo.stat()
        descriptor_metadata = os.fstat(repo_fd)
    except OSError as exc:
        raise HandoffError("The handoff repository path is no longer stable.") from exc
    if (
        not stat.S_ISDIR(path_metadata.st_mode)
        or path_metadata.st_dev != descriptor_metadata.st_dev
        or path_metadata.st_ino != descriptor_metadata.st_ino
    ):
        raise HandoffError("The handoff repository path changed during the operation.")


@contextmanager
def _verified_repo(repo: Path) -> Iterator[tuple[Path, int]]:
    resolved = repo.resolve()
    try:
        repo_fd = os.open(resolved, DIRECTORY_FLAGS)
    except OSError as exc:
        raise HandoffError("The repository root could not be opened safely.") from exc
    try:
        _assert_repo_path(resolved, repo_fd)

        def enter_pinned_repo() -> None:
            os.fchdir(repo_fd)

        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            pass_fds=(repo_fd,),
            preexec_fn=enter_pinned_repo,
        )
        _assert_repo_path(resolved, repo_fd)
        if Path(result.stdout.strip()).resolve() != resolved:
            raise HandoffError("Handoffs must target the exact repository root.")
        yield resolved, repo_fd
    except (OSError, subprocess.CalledProcessError, subprocess.SubprocessError) as exc:
        raise HandoffError("The handoff repository root could not be verified.") from exc
    finally:
        os.close(repo_fd)


def _validate_identity(source: str, destination: str, report_id: str) -> None:
    if not TASK_ID.fullmatch(source) or not TASK_ID.fullmatch(destination):
        raise HandoffError("Source and destination task IDs must be full lowercase UUIDs.")
    if source == destination:
        raise HandoffError("Source and destination task IDs must differ.")
    if not REPORT_ID.fullmatch(report_id):
        raise HandoffError("The report ID contains unsupported characters.")


def _validate_candidate(candidate: str | None) -> None:
    if candidate is not None and not FULL_SHA.fullmatch(candidate):
        raise HandoffError("Candidate SHA must be a full lowercase commit SHA.")


def _open_child_directory(
    parent_fd: int,
    name: str,
    *,
    create: bool,
    private: bool,
) -> int:
    created = False
    try:
        descriptor = os.open(name, DIRECTORY_FLAGS, dir_fd=parent_fd)
    except FileNotFoundError:
        if not create:
            raise HandoffError("The requested handoff directory does not exist.")
        try:
            os.mkdir(name, mode=0o700, dir_fd=parent_fd)
            created = True
        except FileExistsError:
            pass
        try:
            descriptor = os.open(name, DIRECTORY_FLAGS, dir_fd=parent_fd)
        except OSError as exc:
            raise HandoffError("The handoff directory could not be opened safely.") from exc
    except OSError as exc:
        raise HandoffError("The handoff directory could not be opened safely.") from exc

    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISDIR(metadata.st_mode):
            raise HandoffError("The handoff path must contain only directories.")
        if created:
            os.fchmod(descriptor, 0o700)
            metadata = os.fstat(descriptor)
        mode = stat.S_IMODE(metadata.st_mode)
        if private and mode & 0o077:
            raise HandoffError("The handoff directory permissions are too broad.")
        if not private and mode & 0o022:
            raise HandoffError("The .codex directory must not be group- or world-writable.")
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


@contextmanager
def _destination_directory(repo_fd: int, destination: str, *, create: bool) -> Iterator[int]:
    descriptors: list[int] = []
    try:
        codex_fd = _open_child_directory(repo_fd, ".codex", create=create, private=False)
        descriptors.append(codex_fd)
        handoffs_fd = _open_child_directory(codex_fd, "handoffs", create=create, private=True)
        descriptors.append(handoffs_fd)
        destination_fd = _open_child_directory(
            handoffs_fd,
            destination,
            create=create,
            private=True,
        )
        descriptors.append(destination_fd)
        yield destination_fd
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _artifact_relative(destination: str, report_id: str) -> Path:
    return Path(".codex") / "handoffs" / destination / f"{report_id}.json"


def _read_bounded(read: Callable[[int], bytes]) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while total <= MAX_REPORT_BYTES:
        chunk = read(min(64 * 1024, MAX_REPORT_BYTES + 1 - total))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
    if total > MAX_REPORT_BYTES:
        raise HandoffError("The report exceeds the one MiB size limit.")
    return b"".join(chunks)


def _read_report(path: str) -> str:
    try:
        if path == "-":
            stream = getattr(sys.stdin, "buffer", None)
            if stream is None:
                raise HandoffError("The report input must be a binary stream.")
            encoded = _read_bounded(stream.read)
        else:
            nofollow = getattr(os, "O_NOFOLLOW", None)
            nonblocking = getattr(os, "O_NONBLOCK", None)
            if nofollow is None or nonblocking is None:
                raise HandoffError("The platform cannot safely open report inputs.")
            descriptor = os.open(path, os.O_RDONLY | nofollow | nonblocking)
            try:
                metadata = os.fstat(descriptor)
                if not stat.S_ISREG(metadata.st_mode):
                    raise HandoffError("The report input must be a regular file.")
                if stat.S_IMODE(metadata.st_mode) & 0o077:
                    raise HandoffError("The report input permissions are too broad.")
                if metadata.st_size > MAX_REPORT_BYTES:
                    raise HandoffError("The report exceeds the one MiB size limit.")
                encoded = _read_bounded(lambda size: os.read(descriptor, size))
            finally:
                os.close(descriptor)
    except OSError as exc:
        raise HandoffError("The report input could not be read.") from exc
    try:
        report = encoded.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HandoffError("The report input must be valid UTF-8.") from exc
    if not report.strip():
        raise HandoffError("The report must not be empty.")
    return report


def _canonical_digest(document: dict[str, Any]) -> str:
    payload = json.dumps(
        document,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _receipt(document: dict[str, Any]) -> dict[str, Any]:
    return {
        "artifact": str(
            _artifact_relative(document["destination_task_id"], document["report_id"])
        ),
        "candidate_sha": document["candidate_sha"],
        "destination_task_id": document["destination_task_id"],
        "handoff_sha256": document["handoff_sha256"],
        "report_id": document["report_id"],
        "report_sha256": document["report_sha256"],
        "source_task_id": document["source_task_id"],
    }


def _read_artifact(destination_fd: int, filename: str, *, strict: bool = False) -> dict[str, Any]:
    try:
        descriptor = os.open(
            filename,
            os.O_RDONLY | NOFOLLOW | getattr(os, "O_NONBLOCK", 0),
            dir_fd=destination_fd,
        )
    except FileNotFoundError as exc:
        raise HandoffError("The requested handoff artifact does not exist.") from exc
    except OSError as exc:
        raise HandoffError("The handoff artifact could not be opened safely.") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise HandoffError("The handoff artifact must be a regular file.")
        if stat.S_IMODE(metadata.st_mode) & 0o077:
            raise HandoffError("The handoff artifact permissions are too broad.")
        if metadata.st_size > MAX_ARTIFACT_BYTES:
            raise HandoffError("The handoff artifact exceeds the size limit.")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, 65536)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_ARTIFACT_BYTES:
                raise HandoffError("The handoff artifact exceeds the size limit.")
            chunks.append(chunk)
    finally:
        os.close(descriptor)
    try:
        raw = b"".join(chunks).decode("utf-8")
        document = _strict_json(raw) if strict else json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HandoffError("The handoff artifact could not be decoded.") from exc
    if not isinstance(document, dict):
        raise HandoffError("The handoff artifact schema is invalid.")
    return document


def _load_verified(
    repo_fd: int,
    source: str,
    destination: str,
    report_id: str,
    expected_candidate: str | None,
) -> dict[str, Any]:
    _validate_identity(source, destination, report_id)
    _validate_candidate(expected_candidate)
    with _destination_directory(repo_fd, destination, create=False) as destination_fd:
        document = _read_artifact(destination_fd, f"{report_id}.json")
    if document.get("schema") != SCHEMA:
        raise HandoffError("The handoff artifact schema is invalid.")
    if (
        document.get("source_task_id") != source
        or document.get("destination_task_id") != destination
        or document.get("report_id") != report_id
    ):
        raise HandoffError("The handoff artifact identity does not match the request.")

    candidate = document.get("candidate_sha")
    if candidate is not None and (
        not isinstance(candidate, str) or not FULL_SHA.fullmatch(candidate)
    ):
        raise HandoffError("The handoff artifact candidate SHA is invalid.")
    if expected_candidate is not None and candidate != expected_candidate:
        raise HandoffError("The handoff artifact candidate SHA does not match the request.")

    report = document.get("report")
    report_digest = document.get("report_sha256")
    if not isinstance(report, str) or not report.strip() or not isinstance(report_digest, str):
        raise HandoffError("The handoff artifact report is invalid.")
    if hashlib.sha256(report.encode("utf-8")).hexdigest() != report_digest:
        raise HandoffError("The handoff artifact report hash does not match.")

    title = document.get("title")
    if not isinstance(title, str) or not title.strip() or len(title) > 200:
        raise HandoffError("The handoff artifact title is invalid.")
    if not isinstance(document.get("created_at"), str) or not document["created_at"]:
        raise HandoffError("The handoff artifact timestamp is invalid.")

    claimed_digest = document.get("handoff_sha256")
    if not isinstance(claimed_digest, str):
        raise HandoffError("The handoff artifact content hash is invalid.")
    unsigned = dict(document)
    del unsigned["handoff_sha256"]
    if _canonical_digest(unsigned) != claimed_digest:
        raise HandoffError("The handoff artifact content hash does not match.")
    return document


def _write_all(descriptor: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        offset += os.write(descriptor, payload[offset:])


def write(args: argparse.Namespace) -> None:
    _validate_identity(args.source_task_id, args.destination_task_id, args.report_id)
    _validate_candidate(args.candidate_sha)
    if not args.title.strip() or len(args.title) > 200:
        raise HandoffError("The report title must contain 1 to 200 characters.")
    with _verified_repo(args.repo) as (repo, repo_fd):
        report = _read_report(args.report_file)
        _assert_repo_path(repo, repo_fd)
        document: dict[str, Any] = {
            "candidate_sha": args.candidate_sha,
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "destination_task_id": args.destination_task_id,
            "report": report,
            "report_id": args.report_id,
            "report_sha256": hashlib.sha256(report.encode("utf-8")).hexdigest(),
            "schema": SCHEMA,
            "source_task_id": args.source_task_id,
            "title": args.title,
        }
        document["handoff_sha256"] = _canonical_digest(document)
        encoded = (
            json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        if len(encoded) > MAX_ARTIFACT_BYTES:
            raise HandoffError(
                "The serialized handoff artifact exceeds the two MiB size limit."
            )

        artifact_name = f"{args.report_id}.json"
        temporary_name = f".{artifact_name}.{secrets.token_hex(12)}.tmp"
        with _destination_directory(
            repo_fd,
            args.destination_task_id,
            create=True,
        ) as destination_fd:
            temporary_fd: int | None = None
            try:
                temporary_fd = os.open(
                    temporary_name,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | NOFOLLOW,
                    0o600,
                    dir_fd=destination_fd,
                )
                os.fchmod(temporary_fd, 0o600)
                _write_all(temporary_fd, encoded)
                os.fsync(temporary_fd)
                os.close(temporary_fd)
                temporary_fd = None
                os.link(
                    temporary_name,
                    artifact_name,
                    src_dir_fd=destination_fd,
                    dst_dir_fd=destination_fd,
                    follow_symlinks=False,
                )
                os.unlink(temporary_name, dir_fd=destination_fd)
                os.fsync(destination_fd)
                try:
                    _assert_repo_path(repo, repo_fd)
                except HandoffError:
                    os.unlink(artifact_name, dir_fd=destination_fd)
                    os.fsync(destination_fd)
                    raise
            except FileExistsError as exc:
                raise HandoffError(
                    "The handoff artifact already exists and will not be overwritten."
                ) from exc
            except OSError as exc:
                raise HandoffError("The handoff artifact could not be written safely.") from exc
            finally:
                if temporary_fd is not None:
                    os.close(temporary_fd)
                try:
                    os.unlink(temporary_name, dir_fd=destination_fd)
                except FileNotFoundError:
                    pass
                except OSError:
                    pass
    print(json.dumps(_receipt(document), sort_keys=True))


def verify(args: argparse.Namespace) -> None:
    with _verified_repo(args.repo) as (repo, repo_fd):
        document = _load_verified(
            repo_fd,
            args.source_task_id,
            args.destination_task_id,
            args.report_id,
            args.candidate_sha,
        )
        _assert_repo_path(repo, repo_fd)
    print(json.dumps(_receipt(document), sort_keys=True))


def read(args: argparse.Namespace) -> None:
    with _verified_repo(args.repo) as (repo, repo_fd):
        document = _load_verified(
            repo_fd,
            args.source_task_id,
            args.destination_task_id,
            args.report_id,
            args.candidate_sha,
        )
        _assert_repo_path(repo, repo_fd)
    sys.stdout.write(document["report"])
    if not document["report"].endswith("\n"):
        sys.stdout.write("\n")


@contextmanager
def _session_directory(parent_fd: int, name: str) -> Iterator[int]:
    try:
        fd = os.open(name, DIRECTORY_FLAGS, dir_fd=parent_fd)
    except OSError as exc:
        raise HandoffError("The local task-session directory could not be opened safely.") from exc
    try:
        if not stat.S_ISDIR(os.fstat(fd).st_mode):
            raise HandoffError("The local task-session path must contain only directories.")
        yield fd
    finally:
        os.close(fd)


def _session_children(directory_fd: int) -> list[str]:
    try:
        return os.listdir(directory_fd)
    except OSError as exc:
        raise HandoffError("The local task-session directory could not be listed.") from exc


def _find_source_log(root_fd: int, source_task_id: str) -> tuple[str, str, str, str]:
    matches: list[tuple[str, str, str, str]] = []
    suffix = f"-{source_task_id}.jsonl"
    for year in _session_children(root_fd):
        if not re.fullmatch(r"[0-9]{4}", year):
            continue
        with _session_directory(root_fd, year) as year_fd:
            for month in _session_children(year_fd):
                if not re.fullmatch(r"[0-9]{2}", month):
                    continue
                with _session_directory(year_fd, month) as month_fd:
                    for day in _session_children(month_fd):
                        if not re.fullmatch(r"[0-9]{2}", day):
                            continue
                        with _session_directory(month_fd, day) as day_fd:
                            for name in _session_children(day_fd):
                                if name.startswith("rollout-") and name.endswith(suffix):
                                    matches.append((year, month, day, name))
    if len(matches) != 1:
        raise HandoffError("Expected exactly one local log for the source task.")
    return matches[0]


def _assert_session_child(parent_fd: int, name: str, child_fd: int) -> None:
    try:
        path_metadata = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        descriptor_metadata = os.fstat(child_fd)
    except OSError as exc:
        raise HandoffError("The local task-session path changed during the read.") from exc
    if (
        not stat.S_ISDIR(path_metadata.st_mode)
        or path_metadata.st_dev != descriptor_metadata.st_dev
        or path_metadata.st_ino != descriptor_metadata.st_ino
    ):
        raise HandoffError("The local task-session path changed during the read.")


def _load_final(args: argparse.Namespace) -> dict[str, str]:
    """Read only the exact completed turn's final message from a local task log."""
    if not TASK_ID.fullmatch(args.source_task_id) or not TASK_ID.fullmatch(args.turn_id):
        raise HandoffError("Source task and turn IDs must be full lowercase UUIDs.")
    try:
        root = args.sessions_root.resolve(strict=True)
    except OSError as exc:
        raise HandoffError("The local task-session root is unavailable.") from exc
    try:
        root_fd = os.open(root, DIRECTORY_FLAGS)
    except OSError as exc:
        raise HandoffError("The local task-session root could not be opened safely.") from exc
    try:
        if not stat.S_ISDIR(os.fstat(root_fd).st_mode):
            raise HandoffError("The local task-session root is not a directory.")
        year, month, day, name = _find_source_log(root_fd, args.source_task_id)
        with _session_directory(root_fd, year) as year_fd:
            with _session_directory(year_fd, month) as month_fd:
                with _session_directory(month_fd, day) as day_fd:
                    try:
                        fd = os.open(
                            name, os.O_RDONLY | NOFOLLOW | getattr(os, "O_NONBLOCK", 0),
                            dir_fd=day_fd,
                        )
                    except OSError as exc:
                        raise HandoffError("The local task log could not be opened safely.") from exc
                    try:
                        if not stat.S_ISREG(os.fstat(fd).st_mode):
                            raise HandoffError("The local task log must be a regular file.")
                        completions: list[dict[str, str]] = []
                        with os.fdopen(fd, "r", encoding="utf-8") as stream:
                            fd = -1
                            for line in stream:
                                try:
                                    event = json.loads(line)
                                except (json.JSONDecodeError, UnicodeError) as exc:
                                    raise HandoffError("The local task log contains invalid JSON.") from exc
                                if not isinstance(event, dict):
                                    raise HandoffError("The local task log contains an invalid event.")
                                payload = event.get("payload")
                                if (
                                    event.get("type") == "event_msg"
                                    and isinstance(payload, dict)
                                    and payload.get("type") == "task_complete"
                                    and payload.get("turn_id") == args.turn_id
                                ):
                                    message = payload.get("last_agent_message")
                                    timestamp = event.get("timestamp")
                                    if not isinstance(message, str) or not message.strip() or not isinstance(timestamp, str):
                                        raise HandoffError("The completed turn has no readable final message.")
                                    if len(message.encode("utf-8")) > MAX_REPORT_BYTES:
                                        raise HandoffError("The completed turn's final message exceeds the size limit.")
                                    completions.append({"source_task_id": args.source_task_id, "turn_id": args.turn_id, "completed_at": timestamp, "final_message": message})
                    except (OSError, UnicodeError) as exc:
                        raise HandoffError("The local task log could not be read.") from exc
                    finally:
                        if fd >= 0:
                            os.close(fd)
                    _assert_session_child(month_fd, day, day_fd)
                _assert_session_child(year_fd, month, month_fd)
            _assert_session_child(root_fd, year, year_fd)
    finally:
        os.close(root_fd)
    if len(completions) != 1:
        raise HandoffError("Expected exactly one final message for the completed turn.")
    return completions[0]


def read_final(args: argparse.Namespace) -> None:
    print(json.dumps(_load_final(args), sort_keys=True))


def _ack_report_id(report_id: str) -> str:
    return "ack-" + hashlib.sha256(report_id.encode("utf-8")).hexdigest()


def _ack_context(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, str]]:
    with _verified_repo(args.repo) as (repo, repo_fd):
        original = _load_verified(
            repo_fd, args.source_task_id, args.destination_task_id,
            args.report_id, args.candidate_sha,
        )
        _assert_repo_path(repo, repo_fd)
    final_args = argparse.Namespace(
        sessions_root=args.sessions_root,
        source_task_id=args.source_task_id,
        turn_id=args.source_turn_id,
    )
    final = _load_final(final_args)
    # Markdown hard line breaks add spaces before newlines without changing report text.
    def without_hard_breaks(value: str) -> str:
        return re.sub(r" {2}(?=\n)", "", value)

    report = without_hard_breaks(original["report"]).rstrip("\n")
    message = without_hard_breaks(final["final_message"])
    offset = message.find(report)
    while offset >= 0:
        end = offset + len(report)
        if (offset == 0 or message[offset - 1] == "\n") and (end == len(message) or message[end] == "\n"):
            break
        offset = message.find(report, offset + 1)
    if offset < 0:
        raise HandoffError("The completed final message does not contain the verified report.")
    return original, final


def _ack_fields(args: argparse.Namespace, original: dict[str, Any], final: dict[str, str]) -> dict[str, Any]:
    return {
        "schema": ACK_SCHEMA,
        "original_source_task_id": args.source_task_id,
        "original_destination_task_id": args.destination_task_id,
        "original_report_id": args.report_id,
        "candidate_sha": original["candidate_sha"],
        "handoff_sha256": original["handoff_sha256"],
        "report_sha256": original["report_sha256"],
        "source_turn_id": args.source_turn_id,
        "final_message_sha256": hashlib.sha256(final["final_message"].encode("utf-8")).hexdigest(),
        "final_reconciled": True,
    }


def acknowledge(args: argparse.Namespace) -> None:
    """Lead records immutable receipt after checking the source's completed final reply."""
    if not args.confirm_final_reconciled:
        raise HandoffError("The Lead must explicitly confirm final-message reconciliation.")
    original, final = _ack_context(args)
    payload = _ack_fields(args, original, final)
    payload["acknowledged_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", prefix="work-report-ack-", suffix=".json") as report_file:
        json.dump(payload, report_file, sort_keys=True)
        report_file.flush()
        write(argparse.Namespace(
            repo=args.repo,
            source_task_id=args.destination_task_id,
            destination_task_id=args.source_task_id,
            report_id=_ack_report_id(args.report_id),
            candidate_sha=original["candidate_sha"],
            title=f"Acknowledgment for {args.report_id}",
            report_file=report_file.name,
        ))


def verify_ack(args: argparse.Namespace) -> None:
    """Source verifies the Lead receipt is bound to its exact report and final turn."""
    original, final = _ack_context(args)
    with _verified_repo(args.repo) as (repo, repo_fd):
        acknowledgment = _load_verified(
            repo_fd, args.destination_task_id, args.source_task_id,
            _ack_report_id(args.report_id), original["candidate_sha"],
        )
        _assert_repo_path(repo, repo_fd)
    try:
        payload = json.loads(acknowledgment["report"])
    except json.JSONDecodeError as exc:
        raise HandoffError("The acknowledgment report is not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise HandoffError("The acknowledgment report has an invalid schema.")
    expected = _ack_fields(args, original, final)
    if set(payload) != set(expected) | {"acknowledged_at"} or any(
        payload.get(key) != value for key, value in expected.items()
    ):
        raise HandoffError("The acknowledgment does not match the exact report and final turn.")
    if not isinstance(payload.get("acknowledged_at"), str) or not payload["acknowledged_at"]:
        raise HandoffError("The acknowledgment timestamp is invalid.")
    print(json.dumps(_receipt(acknowledgment), sort_keys=True))


# Additive review-specific pilot. Generic v1 commands and records stay intact.
V2 = "xray-mitm-review/v2"
DIGEST = re.compile(r"^[0-9a-f]{64}$")
V2_MARKER = "XRAY_HANDOFF_V2="


def _strict_json(raw: str) -> Any:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise HandoffError("Duplicate JSON field in review evidence.")
            result[key] = value
        return result

    def invalid_constant(value: str) -> None:
        raise HandoffError("Non-finite JSON value in review evidence.")

    try:
        return json.loads(raw, object_pairs_hook=unique, parse_constant=invalid_constant)
    except (ValueError, RecursionError) as exc:
        raise HandoffError("Review evidence is not valid bounded JSON.") from exc


def _v2_name(kind: str, identity: str) -> str:
    if not REPORT_ID.fullmatch(identity):
        raise HandoffError("Invalid review record ID.")
    return f"review-v2-{kind}-{identity}.json"


def _seal(document: dict[str, Any]) -> dict[str, Any]:
    return {**document, "sha256": _canonical_digest(document)}


def _v2_load(fd: int, kind: str, identity: str) -> dict[str, Any]:
    doc = _read_artifact(fd, _v2_name(kind, identity), strict=True)
    unsigned = {k: v for k, v in doc.items() if k != "sha256"}
    if doc.get("schema") != V2 or doc.get("kind") != kind or doc.get("sha256") != _canonical_digest(unsigned):
        raise HandoffError("Review record schema or digest mismatch.")
    return doc


def _v2_save(repo: Path, repo_fd: int, fd: int, kind: str, identity: str,
             payload: dict[str, Any]) -> dict[str, Any]:
    doc = _seal({"schema": V2, "kind": kind, **payload})
    encoded = (json.dumps(doc, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    if len(encoded) > MAX_ARTIFACT_BYTES:
        raise HandoffError("Review record exceeds the artifact size limit.")
    name = _v2_name(kind, identity)
    temp = f".{name}.{secrets.token_hex(12)}.tmp"
    _assert_repo_path(repo, repo_fd)
    descriptor = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | NOFOLLOW, 0o600, dir_fd=fd)
    linked = False
    try:
        os.fchmod(descriptor, 0o600)
        _write_all(descriptor, encoded)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.link(temp, name, src_dir_fd=fd, dst_dir_fd=fd, follow_symlinks=False)
        linked = True
        os.fsync(fd)
        _assert_repo_path(repo, repo_fd)
    except FileExistsError as exc:
        raise HandoffError("Review record already exists; no overwrite permitted.") from exc
    except HandoffError:
        if linked:
            os.unlink(name, dir_fd=fd)
        raise
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.unlink(temp, dir_fd=fd)
    return doc


def _v2_exists(fd: int, kind: str, identity: str) -> bool:
    try:
        os.stat(_v2_name(kind, identity), dir_fd=fd, follow_symlinks=False)
        return True
    except FileNotFoundError:
        return False


@contextmanager
def _v2_store(args: argparse.Namespace, *, create: bool = False) -> Iterator[tuple[Path, int, int]]:
    _validate_identity(args.source_task_id, args.destination_task_id, args.assignment_id)
    with _verified_repo(args.repo) as (repo, repo_fd):
        with _destination_directory(repo_fd, args.destination_task_id, create=create) as fd:
            flags = os.O_RDWR | NOFOLLOW | getattr(os, "O_NONBLOCK", 0)
            lock_fd = os.open("review-v2.lock", flags | (os.O_CREAT if create else 0), 0o600, dir_fd=fd)
            try:
                metadata = os.fstat(lock_fd)
                if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1 or stat.S_IMODE(metadata.st_mode) & 0o077:
                    raise HandoffError("Review lock must be a private regular file.")
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as exc:
                    raise HandoffError("Review store busy; stop, refresh once after current writer finishes.") from exc
                current = os.stat("review-v2.lock", dir_fd=fd, follow_symlinks=False)
                if (current.st_dev, current.st_ino) != (metadata.st_dev, metadata.st_ino):
                    raise HandoffError("Review lock path changed.")
                yield repo, repo_fd, fd
                _assert_repo_path(repo, repo_fd)
                with _destination_directory(repo_fd, args.destination_task_id, create=False) as current_fd:
                    pinned, observed = os.fstat(fd), os.fstat(current_fd)
                    if (pinned.st_dev, pinned.st_ino) != (observed.st_dev, observed.st_ino):
                        raise HandoffError("Review store path changed during operation.")
                current = os.stat("review-v2.lock", dir_fd=fd, follow_symlinks=False)
                if (current.st_dev, current.st_ino) != (metadata.st_dev, metadata.st_ino):
                    raise HandoffError("Review lock path changed.")
            finally:
                os.close(lock_fd)


def _v2_diff(repo_fd: int, repository: str, base: str, head: str) -> str:
    if repository != "duuuude/xray-mitm-openwrt":
        raise HandoffError("Review repository identity must be the canonical GitHub project.")
    if not FULL_SHA.fullmatch(base) or not FULL_SHA.fullmatch(head):
        raise HandoffError("Review base/head must be full commit SHAs.")

    def git(*arguments: str) -> bytes:
        return subprocess.run(["git", *arguments], check=True, stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL, timeout=15, pass_fds=(repo_fd,),
                              preexec_fn=lambda: os.fchdir(repo_fd)).stdout

    allowed = {f"https://github.com/{repository}", f"git@github.com:{repository}",
               f"ssh://git@github.com/{repository}"}
    allowed |= {url + ".git" for url in list(allowed)}
    for flags in ((), ("--push",)):
        urls = git("remote", "get-url", *flags, "--all", "origin").decode("utf-8").splitlines()
        if not urls or any(url not in allowed for url in urls):
            raise HandoffError("Effective review fetch/push remote identity mismatch.")
    for sha in (base, head):
        if git("cat-file", "-t", sha).strip() != b"commit":
            raise HandoffError("Review base/head must identify existing commits.")
    git("merge-base", "--is-ancestor", base, head)
    diff = git("diff", "--binary", "--full-index", "--no-ext-diff", "--no-textconv", "--no-renames", base, head, "--")
    if len(diff) > MAX_REPORT_BYTES:
        raise HandoffError("Review diff exceeds the pilot's one MiB limit.")
    return hashlib.sha256(diff).hexdigest()


def assign_review(args: argparse.Namespace) -> None:
    with _verified_repo(args.repo) as (repo, repo_fd):
        digest = _v2_diff(repo_fd, args.repository, args.base_sha, args.candidate_sha)
        if type(args.pr) is not int or args.pr <= 0 or digest != args.diff_sha256:
            raise HandoffError("Review PR or expected full diff digest mismatch.")
        _assert_repo_path(repo, repo_fd)
    with _v2_store(args, create=True) as (repo, repo_fd, fd):
        doc = _v2_save(repo, repo_fd, fd, "assignment", args.assignment_id, {
            "assignment_id": args.assignment_id, "repository": args.repository,
            "pr": args.pr, "base_sha": args.base_sha, "candidate_sha": args.candidate_sha,
            "diff_sha256": digest, "source_task_id": args.source_task_id,
            "destination_task_id": args.destination_task_id,
        })
    print(json.dumps(doc, sort_keys=True))


def _v2_assignment(args: argparse.Namespace, repo_fd: int, fd: int) -> dict[str, Any]:
    doc = _v2_load(fd, "assignment", args.assignment_id)
    if (not DIGEST.fullmatch(args.assignment_sha256) or doc["sha256"] != args.assignment_sha256
            or doc.get("assignment_id") != args.assignment_id
            or doc.get("source_task_id") != args.source_task_id
            or doc.get("destination_task_id") != args.destination_task_id
            or type(doc.get("pr")) is not int or doc["pr"] <= 0
            or _v2_diff(repo_fd, doc["repository"], doc["base_sha"], doc["candidate_sha"]) != doc["diff_sha256"]):
        raise HandoffError("Review assignment identity or diff mismatch.")
    return doc


def _v2_review_fields(report: Any) -> None:
    required = {"verdict", "findings", "unresolved_conflicts", "supersedes", "analysis"}
    if not isinstance(report, dict) or set(report) != required:
        raise HandoffError("Review requires exactly verdict/findings/unresolved_conflicts/supersedes/analysis.")
    if report["verdict"] not in ("APPROVE", "CHANGES REQUESTED", "BLOCK"):
        raise HandoffError("Invalid review verdict.")
    if not isinstance(report["analysis"], str) or not report["analysis"].strip():
        raise HandoffError("Review analysis must be nonempty.")
    if not isinstance(report["findings"], list) or not isinstance(report["unresolved_conflicts"], list):
        raise HandoffError("Findings and conflicts must be explicit lists.")
    for finding in report["findings"]:
        if (not isinstance(finding, dict) or set(finding) != {"id", "severity", "status", "summary"}
                or finding["severity"] not in ("blocker", "high", "medium", "low")
                or finding["status"] not in ("OPEN", "RESOLVED")
                or any(not isinstance(finding[x], str) or not finding[x].strip() for x in ("id", "summary"))):
            raise HandoffError("Invalid structured review finding.")
    if len({x["id"] for x in report["findings"]}) != len(report["findings"]):
        raise HandoffError("Duplicate finding ID.")
    if any(not isinstance(x, str) or not x.strip() for x in report["unresolved_conflicts"]):
        raise HandoffError("Invalid unresolved conflict.")
    if report["supersedes"] is not None and (not isinstance(report["supersedes"], str) or not REPORT_ID.fullmatch(report["supersedes"])):
        raise HandoffError("Invalid supersession identity.")
    if report["verdict"] == "APPROVE" and (report["unresolved_conflicts"] or any(x["status"] == "OPEN" for x in report["findings"])):
        raise HandoffError("APPROVE cannot coexist with unresolved findings or conflicts.")
    if report["unresolved_conflicts"] and report["verdict"] != "BLOCK":
        raise HandoffError("Unresolved assignment conflicts require BLOCK.")


def _v2_report(args: argparse.Namespace, assignment: dict[str, Any], fd: int,
               *, archived: bool = False) -> dict[str, Any]:
    doc = _v2_load(fd, "report", args.report_id)
    if not archived and _v2_exists(fd, "retraction", args.report_id):
        raise HandoffError("Review is retracted; previous completion/receipt cannot be relied on.")
    node, identity, seen = doc, args.report_id, set()
    while True:
        if identity in seen or len(seen) >= 64:
            raise HandoffError("Ambiguous or excessive review supersession history.")
        seen.add(identity)
        if (node.get("assignment_sha256") != assignment["sha256"] or node.get("report_id") != identity
                or not isinstance(node.get("source_turn_id"), str) or not TASK_ID.fullmatch(node["source_turn_id"])):
            raise HandoffError("Review report assignment/turn mismatch.")
        _v2_review_fields(node["review"])
        prior = node["review"]["supersedes"]
        if prior is None:
            initial = _v2_load(fd, "initial", args.assignment_id)
            if initial.get("report_id") != identity or initial.get("assignment_sha256") != assignment["sha256"]:
                raise HandoffError("Review does not descend from the reserved initial report.")
            break
        parent = _v2_load(fd, "report", prior)
        invalidation = _v2_load(fd, "retraction", prior)
        if (invalidation.get("assignment_sha256") != assignment["sha256"]
                or invalidation.get("report_id") != prior or invalidation.get("report_sha256") != parent["sha256"]
                or invalidation.get("replacement_report_id") != identity):
            raise HandoffError("Review supersession does not bind the original report.")
        node, identity = parent, prior
    return doc


def _v2_receipt(assignment: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    return {"assignment_id": assignment["assignment_id"], "assignment_sha256": assignment["sha256"],
            "report_id": report["report_id"], "report_sha256": report["sha256"],
            "source_turn_id": report["source_turn_id"], "verdict": report["review"]["verdict"]}


def write_review(args: argparse.Namespace) -> None:
    _validate_identity(args.source_task_id, args.destination_task_id, args.report_id)
    if not TASK_ID.fullmatch(args.source_turn_id):
        raise HandoffError("Review source turn must be an exact UUID.")
    review = _strict_json(_read_report(args.report_file))
    _v2_review_fields(review)
    with _v2_store(args) as (repo, repo_fd, fd):
        assignment = _v2_assignment(args, repo_fd, fd)
        prior = review["supersedes"]
        if prior is None:
            # Reserve one initial report; interruption leaves PENDING, not a
            # second competing verdict. Retry may fill only that reserved ID.
            if not _v2_exists(fd, "initial", args.assignment_id):
                _v2_save(repo, repo_fd, fd, "initial", args.assignment_id,
                         {"assignment_sha256": assignment["sha256"], "report_id": args.report_id})
            slot = _v2_load(fd, "initial", args.assignment_id)
            if slot.get("assignment_sha256") != assignment["sha256"] or slot.get("report_id") != args.report_id:
                raise HandoffError("Assignment already has another report; explicit retraction required.")
        else:
            invalidation = _v2_load(fd, "retraction", prior)
            parent = _v2_report(argparse.Namespace(**{**vars(args), "report_id": prior}), assignment, fd, archived=True)
            if (invalidation.get("assignment_sha256") != assignment["sha256"]
                    or invalidation.get("report_sha256") != parent["sha256"]
                    or invalidation.get("replacement_report_id") != args.report_id):
                raise HandoffError("Replacement does not match the explicit retraction.")
        report = _v2_save(repo, repo_fd, fd, "report", args.report_id, {
            "assignment_sha256": assignment["sha256"], "report_id": args.report_id,
            "source_turn_id": args.source_turn_id, "review": review})
    print(json.dumps(_v2_receipt(assignment, report), sort_keys=True))


def verify_review(args: argparse.Namespace) -> None:
    with _v2_store(args) as (_, repo_fd, fd):
        assignment = _v2_assignment(args, repo_fd, fd)
        report = _v2_report(args, assignment, fd)
    print(json.dumps({"receipt": _v2_receipt(assignment, report), "review": report["review"],
                      "completion": "UNPROVEN", "protected_authority": "NONE"}, sort_keys=True))


def render_review(args: argparse.Namespace) -> None:
    with _v2_store(args) as (_, repo_fd, fd):
        assignment = _v2_assignment(args, repo_fd, fd)
        report = _v2_report(args, assignment, fd)
        receipt = _v2_terminal_receipt(args, assignment, report, repo_fd)
    # The analysis prefix is optional in v2, but permits an unchanged v1
    # report body in the same completed final during the dual-path pilot.
    if args.include_analysis:
        print(report["review"]["analysis"].rstrip("\n"))
    print(V2_MARKER + json.dumps(receipt, sort_keys=True))


def _v2_terminal_receipt(args: argparse.Namespace, assignment: dict[str, Any],
                         report: dict[str, Any], repo_fd: int) -> dict[str, Any]:
    receipt = _v2_receipt(assignment, report)
    if args.legacy_v1:
        legacy = _load_verified(repo_fd, args.source_task_id, args.destination_task_id,
                                args.report_id, assignment["candidate_sha"])
        if legacy["report"] != report["review"]["analysis"]:
            raise HandoffError("Pilot v1 report differs from structured review analysis.")
        receipt["legacy_receipt"] = _receipt(legacy)
    return receipt


def retract_review(args: argparse.Namespace) -> None:
    _validate_identity(args.source_task_id, args.destination_task_id, args.replacement_report_id)
    if args.report_id == args.replacement_report_id or not args.reason.strip():
        raise HandoffError("Retraction needs a new report ID and nonempty reason.")
    with _v2_store(args) as (repo, repo_fd, fd):
        assignment = _v2_assignment(args, repo_fd, fd)
        report = _v2_report(args, assignment, fd)
        doc = _v2_save(repo, repo_fd, fd, "retraction", args.report_id, {
            "assignment_sha256": assignment["sha256"], "report_id": args.report_id,
            "report_sha256": report["sha256"], "replacement_report_id": args.replacement_report_id,
            "reason": args.reason})
    print(json.dumps(doc, sort_keys=True))


def complete_review(args: argparse.Namespace) -> None:
    if not args.confirm_final_reconciled:
        raise HandoffError("Lead must reconcile final context before recording pilot completion.")
    with _v2_store(args) as (repo, repo_fd, fd):
        assignment = _v2_assignment(args, repo_fd, fd)
        report = _v2_report(args, assignment, fd)
        if report["source_turn_id"] != args.source_turn_id:
            raise HandoffError("Completed source turn mismatch.")
        final = _load_final(argparse.Namespace(sessions_root=args.sessions_root,
                            source_task_id=args.source_task_id, turn_id=args.source_turn_id))
        message = final["final_message"].strip()
        # Presentation fences/JSON whitespace may vary; additional authored
        # notes are never discarded. Citation metadata is not duplicated in
        # the authoritative structured report; no report reissue for it.
        message = re.sub(r"\n<oai-mem-citation>\s*<citation_entries>[^<>]*</citation_entries>\s*<rollout_ids>[^<>]*</rollout_ids>\s*</oai-mem-citation>\s*$", "", message)
        if message.startswith("```"):
            lines = message.splitlines()
            if lines[0] not in ("```", "```text") or lines[-1] != "```":
                raise HandoffError("Unsupported completion rendering.")
            message = "\n".join(lines[1:-1])
        pieces = message.split(V2_MARKER)
        if len(pieces) != 2:
            raise HandoffError("Expected exactly one generated terminal review receipt.")
        prefix = re.sub(r" {2}(?=\n)", "", pieces[0]).strip()
        analysis = re.sub(r" {2}(?=\n)", "", report["review"]["analysis"]).strip()
        if prefix and prefix != analysis:
            raise HandoffError("Final contains post-report corrections or extra caveats; retract old review.")
        receipt = _v2_terminal_receipt(args, assignment, report, repo_fd)
        if _strict_json(pieces[1]) != receipt:
            raise HandoffError("Final terminal receipt does not match the review.")
        completed = datetime.fromisoformat(final["completed_at"].replace("Z", "+00:00"))
        if completed.utcoffset() is None or completed > datetime.now(timezone.utc):
            raise HandoffError("Invalid terminal completion timestamp.")
        doc = _v2_save(repo, repo_fd, fd, "completion", args.report_id, {
            "assignment_sha256": assignment["sha256"], "report_sha256": report["sha256"],
            "source_turn_id": report["source_turn_id"], "source_task_id": args.source_task_id,
            "completed_at": final["completed_at"], "observer_task_id": args.destination_task_id,
            "legacy_handoff_sha256": receipt.get("legacy_receipt", {}).get("handoff_sha256"),
            "final_reconciled": True})
    print(json.dumps(doc, sort_keys=True))


def _v2_completion(args: argparse.Namespace, assignment: dict[str, Any],
                   report: dict[str, Any], fd: int, repo_fd: int) -> dict[str, Any]:
    doc = _v2_load(fd, "completion", args.report_id)
    if (doc.get("assignment_sha256") != assignment["sha256"] or doc.get("report_sha256") != report["sha256"]
            or doc.get("source_turn_id") != report["source_turn_id"] or doc.get("final_reconciled") is not True
            or doc.get("source_task_id") != args.source_task_id or doc.get("observer_task_id") != args.destination_task_id):
        raise HandoffError("Completion does not bind the exact report/turn/observer.")
    completed = datetime.fromisoformat(doc["completed_at"].replace("Z", "+00:00"))
    if completed.utcoffset() is None or completed > datetime.now(timezone.utc):
        raise HandoffError("Invalid recorded completion timestamp.")
    legacy_digest = doc["legacy_handoff_sha256"]
    if legacy_digest is not None:
        legacy = _load_verified(repo_fd, args.source_task_id, args.destination_task_id,
                                args.report_id, assignment["candidate_sha"])
        if legacy["handoff_sha256"] != legacy_digest or legacy["report"] != report["review"]["analysis"]:
            raise HandoffError("Pilot v1 evidence no longer matches completion.")
    return doc


def receipt_review(args: argparse.Namespace) -> None:
    with _v2_store(args) as (repo, repo_fd, fd):
        assignment = _v2_assignment(args, repo_fd, fd)
        report = _v2_report(args, assignment, fd)
        completion = _v2_completion(args, assignment, report, fd, repo_fd)
        payload = {"assignment_sha256": assignment["sha256"], "report_sha256": report["sha256"],
                   "completion_sha256": completion["sha256"], "received_by_task_id": args.destination_task_id,
                   "receipt_only": True, "protected_authority": "NONE"}
        if args.command == "receipt-review":
            doc = _v2_save(repo, repo_fd, fd, "receipt", args.report_id, payload)
        else:
            doc = _v2_load(fd, "receipt", args.report_id)
            if {k: v for k, v in doc.items() if k not in ("schema", "kind", "sha256")} != payload:
                raise HandoffError("Receipt does not match the exact completed review.")
    print(json.dumps({"receipt": doc, "review_verdict": report["review"]["verdict"],
                      "pilot_only": True, "protected_authority": "NONE"}, sort_keys=True))


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)

    def common(command: argparse.ArgumentParser) -> None:
        command.add_argument("--repo", required=True, type=Path)
        command.add_argument("--source-task-id", required=True)
        command.add_argument("--destination-task-id", required=True)
        command.add_argument("--report-id", required=True)
        command.add_argument("--candidate-sha")

    write_parser = commands.add_parser("write")
    common(write_parser)
    write_parser.add_argument("--title", required=True)
    write_parser.add_argument("--report-file", required=True)
    write_parser.set_defaults(handler=write)

    verify_parser = commands.add_parser("verify")
    common(verify_parser)
    verify_parser.set_defaults(handler=verify)

    read_parser = commands.add_parser("read")
    common(read_parser)
    read_parser.set_defaults(handler=read)

    final_parser = commands.add_parser("read-final")
    final_parser.add_argument("--sessions-root", required=True, type=Path)
    final_parser.add_argument("--source-task-id", required=True)
    final_parser.add_argument("--turn-id", required=True)
    final_parser.set_defaults(handler=read_final)

    for name, handler in (("ack", acknowledge), ("verify-ack", verify_ack)):
        ack_parser = commands.add_parser(name)
        common(ack_parser)
        ack_parser.add_argument("--sessions-root", required=True, type=Path)
        ack_parser.add_argument("--source-turn-id", required=True)
        if name == "ack":
            ack_parser.add_argument("--confirm-final-reconciled", action="store_true")
        ack_parser.set_defaults(handler=handler)
    for name, handler in (("assign-review", assign_review), ("write-review", write_review),
                          ("verify-review", verify_review), ("render-review", render_review),
                          ("retract-review", retract_review), ("complete-review", complete_review),
                          ("receipt-review", receipt_review), ("verify-review-receipt", receipt_review)):
        command = commands.add_parser(name)
        command.add_argument("--repo", required=True, type=Path)
        command.add_argument("--source-task-id", required=True)
        command.add_argument("--destination-task-id", required=True)
        command.add_argument("--assignment-id", required=True)
        if name == "assign-review":
            command.add_argument("--repository", required=True)
            command.add_argument("--pr", required=True, type=int)
            command.add_argument("--base-sha", required=True)
            command.add_argument("--candidate-sha", required=True)
            command.add_argument("--diff-sha256", required=True)
        else:
            command.add_argument("--assignment-sha256", required=True)
            command.add_argument("--report-id", required=True)
        if name == "write-review":
            command.add_argument("--source-turn-id", required=True)
            command.add_argument("--report-file", required=True)
        elif name == "render-review":
            command.add_argument("--include-analysis", action="store_true")
            command.add_argument("--legacy-v1", action="store_true")
        elif name == "complete-review":
            command.add_argument("--legacy-v1", action="store_true")
            command.add_argument("--source-turn-id", required=True)
            command.add_argument("--sessions-root", required=True, type=Path)
            command.add_argument("--confirm-final-reconciled", action="store_true")
        elif name == "retract-review":
            command.add_argument("--replacement-report-id", required=True)
            command.add_argument("--reason", required=True)
        command.set_defaults(handler=handler)
    return result


def main() -> int:
    try:
        args = parser().parse_args()
        args.handler(args)
    except HandoffError as exc:
        print(f"work-report-handoff: {exc}", file=sys.stderr)
        return 1
    except (OSError, KeyError, TypeError, ValueError, subprocess.SubprocessError) as exc:
        # Bounded fail-closed diagnostics; do not print arbitrary input or
        # captured Git/session output on malformed v2 evidence.
        print(f"work-report-handoff: evidence operation failed ({type(exc).__name__}).", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
