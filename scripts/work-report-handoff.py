#!/usr/bin/env python3
"""Write and verify durable, local-only Work report handoff artifacts."""

from __future__ import annotations

import argparse
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
from typing import Any, Iterator


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


def _read_report(path: str) -> str:
    try:
        if path == "-":
            report = sys.stdin.read()
        else:
            report = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise HandoffError("The report input could not be read.") from exc
    encoded = report.encode("utf-8")
    if not report.strip():
        raise HandoffError("The report must not be empty.")
    if len(encoded) > MAX_REPORT_BYTES:
        raise HandoffError("The report exceeds the one MiB size limit.")
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


def _read_artifact(destination_fd: int, filename: str) -> dict[str, Any]:
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
        document = json.loads(b"".join(chunks).decode("utf-8"))
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


def _load_final(args: argparse.Namespace) -> dict[str, str]:
    """Read only the exact completed turn's final message from a local task log."""
    if not TASK_ID.fullmatch(args.source_task_id) or not TASK_ID.fullmatch(args.turn_id):
        raise HandoffError("Source task and turn IDs must be full lowercase UUIDs.")
    try:
        root = args.sessions_root.resolve(strict=True)
    except OSError as exc:
        raise HandoffError("The local task-session root is unavailable.") from exc
    if not root.is_dir():
        raise HandoffError("The local task-session root is not a directory.")
    matches = list(root.glob(f"*/*/*/rollout-*-{args.source_task_id}.jsonl"))
    if len(matches) != 1:
        raise HandoffError("Expected exactly one local log for the source task.")
    path = matches[0]
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        raise HandoffError("The local task log must not be a symlink.")
    try:
        fd = os.open(path, os.O_RDONLY | NOFOLLOW | getattr(os, "O_NONBLOCK", 0))
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
    if original["report"] not in final["final_message"]:
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
    return result


def main() -> int:
    try:
        args = parser().parse_args()
        args.handler(args)
    except HandoffError as exc:
        print(f"work-report-handoff: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
