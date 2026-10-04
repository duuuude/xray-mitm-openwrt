#!/usr/bin/env python3
"""Schema, provenance, and package-checksum tests for PR evidence artifacts."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
WRITER = ROOT / "scripts/pr-evidence.py"
BASE = "25.12.5"
ARCH = "aarch64_generic"


class PrEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = {key: value for key, value in os.environ.items() if not key.startswith("GITHUB_")}
        self.env["GITHUB_TOKEN"] = "PR_EVIDENCE_SECRET_SENTINEL"
        self.repo = self.root / "repo"
        self.repo.mkdir()
        (self.repo / ".github/workflows").mkdir(parents=True)
        for workflow in ("build.yml", "build-24-10.yml"):
            shutil.copy2(ROOT / ".github/workflows" / workflow,
                         self.repo / ".github/workflows" / workflow)
        (self.repo / "README.md").write_text("base\n", encoding="utf-8")
        self.git("init", "-b", "main")
        self.git("config", "user.email", "evidence@example.invalid")
        self.git("config", "user.name", "PR Evidence Test")
        self.git("add", ".")
        self.git("commit", "-m", "prepare evidence fixture")
        self.base_sha = self.git("rev-parse", "HEAD")
        (self.repo / "docs").mkdir()
        (self.repo / "docs/guide.md").write_text("candidate\n", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-m", "change documentation")
        self.candidate_sha = self.git("rev-parse", "HEAD")
        self.events = self.root / "events.jsonl"
        self.evidence = self.root / "pr-evidence.json"
        self.record("Full repository validation", "sh scripts/validate-release.sh")
        for name in ("Exact base/candidate whitespace check", "Post-validation working-tree check", "Post-validation HEAD check"):
            self.record(name, "fixture check")

    def git(self, *args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(self.repo), *args],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return result.stdout.strip()

    def run_writer(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["python3", str(WRITER), *args],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            env=self.env,
        )

    def record(self, name: str, command: str, result: str = "PASS", exit_code: int = 0) -> None:
        output = self.run_writer(
            "record",
            "--events", str(self.events),
            "--name", name,
            "--command", command,
            "--result", result,
            "--exit-code", str(exit_code),
            "--blocking",
        )
        self.assertEqual(output.returncode, 0, output.stderr)

    def create(self, *, result: str = "READY_FOR_REVIEW", openwrt: str = "not_required") -> subprocess.CompletedProcess[str]:
        return self.run_writer(
            "create",
            "--repo", str(self.repo),
            "--output", str(self.evidence),
            "--events", str(self.events),
            "--base-sha", self.base_sha,
            "--candidate-sha", self.candidate_sha,
            "--categories", "documentation",
            "--result", result,
            "--openwrt", openwrt,
        )

    def write_checksums(self, artifact: Path, names: list[str], *, apk: bool) -> None:
        package_lines = [
            f"{hashlib.sha256((artifact / name).read_bytes()).hexdigest()}  {name}"
            for name in sorted(names)
        ]
        (artifact / "SHA256SUMS").write_text(
            "\n".join(package_lines + ([
                f"{hashlib.sha256((artifact / 'packages.adb').read_bytes()).hexdigest()}  packages.adb"
            ] if apk else [])) + "\n",
            encoding="utf-8",
        )
        if apk:
            (artifact / "PACKAGE_SHA256SUMS").write_text(
                "\n".join(package_lines) + "\n", encoding="utf-8"
            )

    def package_fixture(self, package_format: str) -> Path:
        artifact = self.root / f"{package_format}-dist"
        artifact.mkdir()
        if package_format == "apk":
            package_bytes = {
                "xray-mitm-1.0.apk": b"core apk bytes",
                "luci-app-xray-mitm-1.0.apk": b"luci apk bytes",
            }
            (artifact / "packages.adb").write_bytes(b"unsigned package index")
            release, architecture = "25.12.5", "aarch64_generic"
        else:
            package_bytes = {
                "xray-mitm_1.0_all.ipk": b"core ipk bytes",
                "luci-app-xray-mitm_1.0_all.ipk": b"luci ipk bytes",
            }
            release, architecture = "24.10.8", "aarch64_cortex-a53"
        for name, content in package_bytes.items():
            (artifact / name).write_bytes(content)
        (artifact / "SOURCE_COMMIT").write_text(self.candidate_sha + "\n", encoding="utf-8")
        (artifact / "OPENWRT_RELEASE").write_text(release + "\n", encoding="utf-8")
        (artifact / "SDK_ARCH").write_text(architecture + "\n", encoding="utf-8")
        (artifact / "PACKAGE_FORMAT").write_text(package_format + "\n", encoding="utf-8")
        (artifact / "PACKAGES").write_text("\n".join(sorted(package_bytes)) + "\n", encoding="utf-8")
        self.write_checksums(artifact, list(package_bytes), apk=package_format == "apk")
        return artifact

    def attach_build(self, artifact: Path, package_format: str, release: str, architecture: str) -> subprocess.CompletedProcess[str]:
        return self.run_writer(
            "attach-build",
            "--repo", str(self.repo),
            "--evidence", str(self.evidence),
            "--artifact-dir", str(artifact),
            "--source-sha", self.candidate_sha,
            "--format", package_format,
            "--release", release,
            "--architecture", architecture,
            "--workflow", f"Build OpenWrt {package_format.upper()}",
            "--run-id", "987654321",
            "--sdk-action", "openwrt/gh-action-sdk@7fc2640243284ecc44f4a9c3f749a61746ee02cb",
            "--checksum-command", "sha256sum -c SHA256SUMS",
        )

    def test_create_is_versioned_deterministic_and_secret_free(self) -> None:
        first = self.create()
        self.assertEqual(first.returncode, 0, first.stderr)
        initial = self.evidence.read_bytes()
        document = json.loads(initial)
        self.assertEqual(document["schema_version"], 1)
        self.assertEqual(document["candidate"]["base_sha"], self.base_sha)
        self.assertEqual(document["candidate"]["candidate_sha"], self.candidate_sha)
        self.assertEqual(document["candidate"]["changed_files"], ["docs/guide.md"])
        self.assertEqual(document["checks"][0]["command"], "sh scripts/validate-release.sh")
        self.assertEqual(document["manual_gates"][0]["owner"], "Router & Release Validation")
        self.assertNotIn("PR_EVIDENCE_SECRET_SENTINEL", initial.decode("utf-8"))
        self.assertEqual(self.create().returncode, 0)
        self.assertEqual(self.evidence.read_bytes(), initial)

    def verify_source(self, *, base: str | None = None) -> subprocess.CompletedProcess[str]:
        return self.run_writer("verify-source", "--repo", str(self.repo),
                               "--evidence", str(self.evidence),
                               "--base-sha", base or self.base_sha,
                               "--candidate-sha", self.candidate_sha)

    def test_verify_source_accepts_offline_success_without_claiming_sdk_completion(self) -> None:
        self.assertEqual(self.create().returncode, 0)
        self.assertEqual(self.verify_source().returncode, 0)
        document = json.loads(self.evidence.read_text())
        self.assertTrue(all(item["status"] == "not_required" and not item["performed"]
                            for item in document["package_gates"]))
        self.assertEqual(self.create(result="BLOCKED", openwrt="required").returncode, 0)
        self.assertEqual(self.verify_source().returncode, 0)
        self.assertEqual(json.loads(self.evidence.read_text())["result"], "BLOCKED")

    def test_verify_source_rejects_stale_identity_missing_evidence_and_bad_json(self) -> None:
        self.assertNotEqual(self.verify_source().returncode, 0)
        self.assertEqual(self.create().returncode, 0)
        self.assertNotEqual(self.verify_source(base=self.candidate_sha).returncode, 0)
        document = json.loads(self.evidence.read_text())
        document["candidate"]["candidate_sha"] = self.base_sha
        self.evidence.write_text(json.dumps(document))
        self.assertNotEqual(self.verify_source().returncode, 0)
        for bad in ("{", "[]", "null"):
            self.evidence.write_text(bad)
            result = self.verify_source()
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("Traceback", result.stderr)

    def test_verify_source_rejects_incomplete_checks_and_false_gate_claims(self) -> None:
        self.assertEqual(self.create().returncode, 0)
        initial = self.evidence.read_text()
        mutations = (
            lambda d: d.update(checks=[]),
            lambda d: d["checks"][0].update(result="SKIPPED", blocking=False),
            lambda d: d["checks"][0].update(result="FAIL", exit_code=1),
            lambda d: d["checks"][0].update(exit_code=True),
            lambda d: d["checks"][1].update(result="SKIPPED", blocking=True),
            lambda d: d["checks"].append({"name": "Full-validator LuCI JavaScript syntax",
                                          "command": "node --check", "result": "SKIPPED", "blocking": False}),
            lambda d: d.update(manual_gates=[]),
            lambda d: d["manual_gates"][0].update(performed=True),
            lambda d: d["manual_gates"][0].update(status="required"),
            lambda d: d.update(package_gates=[]),
            lambda d: d["package_gates"][0].update(performed=0),
            lambda d: d["candidate"].update(changed_files=["wrong-path"]),
        )
        for index, mutate in enumerate(mutations):
            with self.subTest(case=index):
                document = json.loads(initial)
                mutate(document)
                self.evidence.write_text(json.dumps(document))
                result = self.verify_source()
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("Traceback", result.stderr)

    def test_source_evidence_is_bound_to_ci_run_and_release_preparation_event(self) -> None:
        (self.repo / "CHANGELOG.md").write_text("release fixture\n")
        self.git("add", ".")
        self.git("commit", "-m", "release preparation fixture")
        self.candidate_sha = self.git("rev-parse", "HEAD")
        for event, expected in (("push", "required"), ("pull_request", "not_required")):
            with self.subTest(event=event), patch.dict(self.env, {"GITHUB_EVENT_NAME": event,
                                                                  "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1"}):
                result = self.create()
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.verify_source().returncode, 0)
                document = json.loads(self.evidence.read_text())
                self.assertEqual(document["package_gates"][0]["status"], expected)
                document["ci"]["run_id"] = "older-run"
                self.evidence.write_text(json.dumps(document))
                self.assertNotEqual(self.verify_source().returncode, 0)

    def test_exact_diff_paths_are_not_reinterpreted_as_quoted_git_output(self) -> None:
        (self.repo / "docs/راهنما.md").write_text("fixture\n")
        self.git("add", ".")
        self.git("commit", "-m", "non-ASCII documentation fixture")
        self.candidate_sha = self.git("rev-parse", "HEAD")
        self.assertEqual(self.create().returncode, 0)
        self.assertEqual(self.verify_source().returncode, 0)

    def test_package_gates_follow_actual_workflow_filters_and_reject_unknown_syntax(self) -> None:
        for path, expected in (("scripts/example.sh", ["required", "not_required"]),
                               ("tests/example.py", ["required", "not_required"]),
                               ("xray-mitm/Makefile", ["required", "required"]),
                               (".github/workflows/build.yml", ["required", "not_required"]),
                               ("docs/ai/MASTER_PLAN.md", ["not_required", "not_required"])):
            with self.subTest(path=path):
                self.git("reset", "--hard", self.candidate_sha)
                file = self.repo / path
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text("fixture\n")
                self.git("add", ".")
                self.git("commit", "-m", "change path fixture")
                old_candidate = self.candidate_sha
                self.candidate_sha = self.git("rev-parse", "HEAD")
                if path.endswith("build.yml"):
                    # Keep valid scheduling syntax while changing the workflow.
                    self.git("reset", "--hard", old_candidate)
                    file.write_text((ROOT / path).read_text() + "\n# fixture\n")
                    self.git("add", ".")
                    self.git("commit", "-m", "change workflow fixture")
                    self.candidate_sha = self.git("rev-parse", "HEAD")
                self.assertEqual(self.create().returncode, 0)
                gates = json.loads(self.evidence.read_text())["package_gates"]
                self.assertEqual([gate["status"] for gate in gates], expected)
                self.assertTrue(all(gate["performed"] is False for gate in gates))
                self.git("reset", "--hard", old_candidate)
                self.candidate_sha = old_candidate
        workflow = self.repo / ".github/workflows/build.yml"
        workflow.write_text(workflow.read_text().replace('"ci/**"', '"ci/*.py"'))
        self.git("add", ".")
        self.git("commit", "-m", "unsupported filter")
        self.candidate_sha = self.git("rev-parse", "HEAD")
        self.assertNotEqual(self.create().returncode, 0)

    def test_required_router_gate_cannot_claim_review_ready(self) -> None:
        blocked = self.create(result="BLOCKED", openwrt="required")
        self.assertEqual(blocked.returncode, 0, blocked.stderr)
        doc = json.loads(self.evidence.read_text(encoding="utf-8"))
        self.assertEqual(doc["result"], "BLOCKED")
        self.assertEqual(doc["manual_gates"][0]["status"], "required")
        self.assertFalse(doc["manual_gates"][0]["performed"])

    def test_failed_check_requires_failed_final_result(self) -> None:
        self.record("Fixture failing command", "false", "FAIL", 1)
        mismatch = self.create()
        self.assertNotEqual(mismatch.returncode, 0)
        failed = self.create(result="FAILED")
        self.assertEqual(failed.returncode, 0, failed.stderr)

    def test_attach_build_records_exact_apk_hashes(self) -> None:
        self.assertEqual(self.create(result="BLOCKED", openwrt="required").returncode, 0)
        artifact = self.package_fixture("apk")
        result = self.attach_build(artifact, "apk", "25.12.5", "aarch64_generic")
        self.assertEqual(result.returncode, 0, result.stderr)
        doc = json.loads(self.evidence.read_text(encoding="utf-8"))
        self.assertEqual(doc["builds"][0]["source_sha"], self.candidate_sha)
        self.assertEqual(doc["builds"][0]["sdk_inputs"]["ARCH"], "aarch64_generic-25.12.5")
        self.assertEqual(doc["builds"][0]["sdk_inputs"]["INDEX"], "1")
        self.assertEqual(
            {item["name"] for item in doc["artifacts"]},
            {"xray-mitm-1.0.apk", "luci-app-xray-mitm-1.0.apk", "packages.adb"},
        )
        expected = hashlib.sha256((artifact / "xray-mitm-1.0.apk").read_bytes()).hexdigest()
        recorded = next(item for item in doc["artifacts"] if item["name"] == "xray-mitm-1.0.apk")
        self.assertEqual(recorded["sha256"], expected)
        self.assertTrue(any(item.get("kind") == "github_action" for item in doc["checks"]))

    def test_attach_build_rejects_tampered_ipk_and_candidate_mismatch(self) -> None:
        self.assertEqual(self.create(result="BLOCKED", openwrt="required").returncode, 0)
        artifact = self.package_fixture("ipk")
        (artifact / "xray-mitm_1.0_all.ipk").write_bytes(b"tampered bytes")
        bad_hash = self.attach_build(artifact, "ipk", "24.10.8", "aarch64_cortex-a53")
        self.assertNotEqual(bad_hash.returncode, 0)

        (artifact / "xray-mitm_1.0_all.ipk").write_bytes(b"core ipk bytes")
        self.write_checksums(
            artifact,
            ["xray-mitm_1.0_all.ipk", "luci-app-xray-mitm_1.0_all.ipk"],
            apk=False,
        )
        mismatch = self.attach_build(artifact, "ipk", "24.10.8", "aarch64_cortex-a53")
        self.assertEqual(mismatch.returncode, 0, mismatch.stderr)
        wrong_candidate = self.run_writer(
            "attach-build",
            "--repo", str(self.repo),
            "--evidence", str(self.evidence),
            "--artifact-dir", str(artifact),
            "--source-sha", self.base_sha,
            "--format", "ipk",
            "--release", "24.10.8",
            "--architecture", "aarch64_cortex-a53",
            "--workflow", "Build OpenWrt IPKs",
            "--run-id", "987654321",
            "--sdk-action", "openwrt/gh-action-sdk@7fc2640243284ecc44f4a9c3f749a61746ee02cb",
            "--checksum-command", "sha256sum -c SHA256SUMS",
        )
        self.assertNotEqual(wrong_candidate.returncode, 0)


if __name__ == "__main__":
    unittest.main()
