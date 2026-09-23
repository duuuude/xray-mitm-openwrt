#!/usr/bin/env python3
"""Behavior tests for the fail-closed local router staging guard."""

from __future__ import annotations

import hashlib
import os
import shlex
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "scripts/router-backup-guard.sh"
CORE_FILES = (
    "passwall2",
    "xray-mitmctl",
    "xray-mitm.uc",
    "overview.js",
    "state.js",
)
CANDIDATE_FILES = (*CORE_FILES, "ui.js")
LIVE_PATHS = {
    "passwall2": "usr/libexec/xray-mitm/passwall2",
    "xray-mitmctl": "usr/sbin/xray-mitmctl",
    "xray-mitm.uc": "usr/share/rpcd/ucode/xray-mitm.uc",
    "overview.js": "www/luci-static/resources/view/xray-mitm/overview.js",
    "state.js": "www/luci-static/resources/xray-mitm/state.js",
    "ui.js": "www/luci-static/resources/xray-mitm/ui.js",
}


class RouterBackupGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.router_root = self.root / "router"
        self.backup = self.router_root / "protected-backup"
        self.router_root.mkdir()
        self.baseline: dict[str, bytes] = {}
        self.candidate: dict[str, bytes] = {}
        for name in CANDIDATE_FILES:
            self.baseline[name] = f"baseline:{name}\n".encode()
            self.candidate[name] = f"candidate:{name}\n".encode()
            if name != "ui.js":
                self.live_file(name).parent.mkdir(parents=True, exist_ok=True)
                self.live_file(name).write_bytes(self.baseline[name])
        self.live_file("ui.js").parent.mkdir(parents=True, exist_ok=True)
        self.live_file("ui.js").write_bytes(self.baseline["ui.js"])
        self.stage = self.root / "stage"
        self.stage.mkdir()
        for name in CANDIDATE_FILES:
            (self.stage / name).write_bytes(self.candidate[name])

    def live_file(self, name: str) -> Path:
        return self.router_root / LIVE_PATHS[name]

    def run_guard(
        self,
        operation: str,
        stage: Path | None = None,
        fake_owner_path: Path | None = None,
        fake_owner_uid: int | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["ROUTER_GUARD_ROOT"] = str(self.router_root)
        if fake_owner_path is not None:
            real_stat = shutil.which("stat")
            self.assertIsNotNone(real_stat)
            fake_bin = self.root / "fake-bin"
            fake_bin.mkdir(exist_ok=True)
            stat_wrapper = fake_bin / "stat"
            stat_wrapper.write_text(
                "#!/bin/sh\n"
                f"REAL_STAT={shlex.quote(str(real_stat))}\n"
                "output=$(\"$REAL_STAT\" \"$@\") || exit $?\n"
                "if [ \"$#\" -eq 3 ] && [ \"$3\" = \"$ROUTER_GUARD_FAKE_OWNER_PATH\" ]; then\n"
                "  set -- $output\n"
                "  printf '%s %s\\n' \"$ROUTER_GUARD_FAKE_OWNER_UID\" \"$2\"\n"
                "else\n"
                "  printf '%s\\n' \"$output\"\n"
                "fi\n",
                encoding="utf-8",
            )
            stat_wrapper.chmod(0o755)
            env["PATH"] = str(fake_bin) + os.pathsep + env.get("PATH", "")
        env["ROUTER_GUARD_FAKE_OWNER_PATH"] = str(fake_owner_path)
        env["ROUTER_GUARD_FAKE_OWNER_UID"] = str(fake_owner_uid)
        command = ["sh", str(GUARD), str(self.backup), operation]
        if stage is not None:
            command.append(str(stage))
        return subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            check=False,
        )

    def write_backup(self, ui_absent: bool = False) -> None:
        self.backup.mkdir(mode=0o700)
        for name in CORE_FILES:
            (self.backup / name).write_bytes(self.baseline[name])
        manifest_names = list(CORE_FILES)
        if ui_absent:
            (self.backup / "ui.js.absent").write_bytes(b"")
            manifest_names.append("ui.js.absent")
        else:
            (self.backup / "ui.js").write_bytes(self.baseline["ui.js"])
            manifest_names.append("ui.js")
        lines = []
        for name in manifest_names:
            digest = hashlib.sha256((self.backup / name).read_bytes()).hexdigest()
            lines.append(f"{digest}  {name}\n")
        (self.backup / "SHA256SUMS").write_text("".join(lines), encoding="ascii")

    def arm_candidate(self) -> None:
        result = self.run_guard("arm", self.stage)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_new_backup_captures_exact_current_live_files(self) -> None:
        result = self.run_guard("protect")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for name in CANDIDATE_FILES:
            self.assertEqual((self.backup / name).read_bytes(), self.baseline[name])
        self.assertIn("ui.js", (self.backup / "SHA256SUMS").read_text(encoding="ascii"))
        checked = self.run_guard("check")
        self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

    def test_backup_path_rejects_parent_component(self) -> None:
        unsafe_backup = self.root / ".." / "outside-backup"
        env = os.environ.copy()
        env["ROUTER_GUARD_ROOT"] = str(self.router_root)
        result = subprocess.run(
            ["sh", str(GUARD), str(unsafe_backup), "protect"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("parent-directory component", result.stderr)

    def test_stale_ui_absent_manifest_is_rejected_without_mutation(self) -> None:
        self.write_backup(ui_absent=True)
        manifest_before = (self.backup / "SHA256SUMS").read_bytes()
        live_before = {name: self.live_file(name).read_bytes() for name in CANDIDATE_FILES}

        result = self.run_guard("protect")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("marks ui.js absent", result.stderr)
        self.assertEqual((self.backup / "SHA256SUMS").read_bytes(), manifest_before)
        self.assertFalse((self.backup / "ACTIVE_STAGE").exists())
        for name, contents in live_before.items():
            self.assertEqual(self.live_file(name).read_bytes(), contents)

    def test_stale_core_backup_is_rejected_without_refreshing_it(self) -> None:
        self.write_backup()
        (self.backup / "overview.js").write_bytes(b"older saved overview\n")
        digest = hashlib.sha256((self.backup / "overview.js").read_bytes()).hexdigest()
        manifest = (self.backup / "SHA256SUMS").read_text(encoding="ascii")
        old_digest = hashlib.sha256(self.baseline["overview.js"]).hexdigest()
        (self.backup / "SHA256SUMS").write_text(
            manifest.replace(old_digest, digest), encoding="ascii"
        )
        backup_before = {path.name: path.read_bytes() for path in self.backup.iterdir()}

        result = self.run_guard("protect")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("stale for overview.js", result.stderr)
        self.assertEqual(
            {path.name: path.read_bytes() for path in self.backup.iterdir()},
            backup_before,
        )
        self.assertEqual(self.live_file("overview.js").read_bytes(), self.baseline["overview.js"])

    def test_protect_refuses_group_writable_existing_backup_directory(self) -> None:
        self.write_backup()
        self.backup.chmod(0o770)
        live_before = {name: self.live_file(name).read_bytes() for name in CANDIDATE_FILES}

        result = self.run_guard("protect")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("protected directory is group/other writable", result.stderr)
        self.assertFalse((self.backup / "ACTIVE_STAGE").exists())
        for name, contents in live_before.items():
            self.assertEqual(self.live_file(name).read_bytes(), contents)

    def test_arm_refuses_group_writable_existing_backup_before_staging(self) -> None:
        self.write_backup()
        self.backup.chmod(0o770)
        live_before = {name: self.live_file(name).read_bytes() for name in CANDIDATE_FILES}

        result = self.run_guard("arm", self.stage)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("protected directory is group/other writable", result.stderr)
        self.assertFalse((self.backup / "ACTIVE_STAGE").exists())
        for name, contents in live_before.items():
            self.assertEqual(self.live_file(name).read_bytes(), contents)

    def test_restore_refuses_group_writable_backup_before_touching_live_files(self) -> None:
        self.assertEqual(self.run_guard("protect").returncode, 0)
        self.arm_candidate()
        for name in CANDIDATE_FILES:
            self.live_file(name).write_bytes(self.candidate[name])
        self.backup.chmod(0o770)
        live_before = {name: self.live_file(name).read_bytes() for name in CANDIDATE_FILES}

        result = self.run_guard("restore")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("protected directory is group/other writable", result.stderr)
        self.assertTrue((self.backup / "ACTIVE_STAGE").is_file())
        for name, contents in live_before.items():
            self.assertEqual(self.live_file(name).read_bytes(), contents)

    def test_protect_refuses_group_writable_backup_file_with_valid_manifest(self) -> None:
        self.write_backup()
        (self.backup / "overview.js").chmod(0o660)
        live_before = {name: self.live_file(name).read_bytes() for name in CANDIDATE_FILES}

        result = self.run_guard("protect")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("protected backup file is group/other writable", result.stderr)
        for name, contents in live_before.items():
            self.assertEqual(self.live_file(name).read_bytes(), contents)

    def test_protect_refuses_unexpected_backup_entries(self) -> None:
        self.write_backup()
        (self.backup / "unexpected.txt").write_text("not in the baseline manifest", encoding="utf-8")

        result = self.run_guard("protect")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unexpected entry", result.stderr)

    def test_backup_parent_rejects_group_writable_directory(self) -> None:
        parent = self.router_root / "untrusted-parent"
        parent.mkdir(mode=0o770)
        self.backup = parent / "protected-backup"
        self.write_backup()
        parent.chmod(0o770)
        live_before = {name: self.live_file(name).read_bytes() for name in CANDIDATE_FILES}

        result = self.run_guard("protect")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("protected directory is group/other writable", result.stderr)
        for name, contents in live_before.items():
            self.assertEqual(self.live_file(name).read_bytes(), contents)

    def test_backup_parent_rejects_symlink_component(self) -> None:
        target = self.router_root / "real-parent"
        target.mkdir()
        link = self.router_root / "linked-parent"
        link.symlink_to(target, target_is_directory=True)
        self.backup = link / "protected-backup"

        result = self.run_guard("protect")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("symlink", result.stderr)
        self.assertFalse((target / "protected-backup").exists())

    def test_missing_backup_parent_is_not_created_implicitly(self) -> None:
        missing_parent = self.router_root / "missing-parent"
        self.backup = missing_parent / "protected-backup"

        result = self.run_guard("protect")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing, not a directory, or a symlink", result.stderr)
        self.assertFalse(missing_parent.exists())

    def test_backup_file_with_untrusted_owner_is_rejected(self) -> None:
        self.write_backup()

        result = self.run_guard(
            "protect",
            fake_owner_path=self.backup / "overview.js",
            fake_owner_uid=os.getuid() + 1,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("protected backup file is not owned by trusted uid", result.stderr)

    def test_backup_with_untrusted_owner_is_rejected(self) -> None:
        self.write_backup()

        result = self.run_guard(
            "protect",
            fake_owner_path=self.backup,
            fake_owner_uid=os.getuid() + 1,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("protected directory is not owned by trusted uid", result.stderr)

    def test_backup_parent_with_untrusted_owner_is_rejected(self) -> None:
        parent = self.router_root / "untrusted-parent"
        parent.mkdir(mode=0o700)
        self.backup = parent / "protected-backup"

        result = self.run_guard(
            "protect",
            fake_owner_path=parent,
            fake_owner_uid=os.getuid() + 1,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("protected directory is not owned by trusted uid", result.stderr)
        self.assertFalse(self.backup.exists())
    def test_restore_accepts_exact_candidate_and_removes_active_marker(self) -> None:
        self.assertEqual(self.run_guard("protect").returncode, 0)
        self.arm_candidate()
        for name in CANDIDATE_FILES:
            self.live_file(name).write_bytes(self.candidate[name])

        result = self.run_guard("restore")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for name in CANDIDATE_FILES:
            self.assertEqual(self.live_file(name).read_bytes(), self.baseline[name])
        self.assertFalse((self.backup / "ACTIVE_STAGE").exists())

    def test_restore_recovers_a_known_partial_stage(self) -> None:
        self.assertEqual(self.run_guard("protect").returncode, 0)
        self.arm_candidate()
        for name in ("passwall2", "overview.js", "ui.js"):
            self.live_file(name).write_bytes(self.candidate[name])

        result = self.run_guard("restore")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for name in CANDIDATE_FILES:
            self.assertEqual(self.live_file(name).read_bytes(), self.baseline[name])

    def test_restore_refuses_unknown_newer_live_file_without_overwrite(self) -> None:
        self.assertEqual(self.run_guard("protect").returncode, 0)
        self.arm_candidate()
        for name in CANDIDATE_FILES:
            self.live_file(name).write_bytes(self.candidate[name])
        self.live_file("overview.js").write_bytes(b"unknown newer live content\n")
        live_before = {name: self.live_file(name).read_bytes() for name in CANDIDATE_FILES}

        result = self.run_guard("restore")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("neither saved baseline nor staged candidate", result.stderr)
        self.assertTrue((self.backup / "ACTIVE_STAGE").is_file())
        for name, contents in live_before.items():
            self.assertEqual(self.live_file(name).read_bytes(), contents)

    def test_absent_baseline_ui_is_restored_as_absent(self) -> None:
        self.live_file("ui.js").unlink()
        self.assertEqual(self.run_guard("protect").returncode, 0)
        self.assertTrue((self.backup / "ui.js.absent").is_file())
        self.arm_candidate()
        for name in CANDIDATE_FILES:
            self.live_file(name).write_bytes(self.candidate[name])

        result = self.run_guard("restore")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(self.live_file("ui.js").exists())
        for name in CORE_FILES:
            self.assertEqual(self.live_file(name).read_bytes(), self.baseline[name])

    def test_second_stage_is_refused_until_first_candidate_is_restored(self) -> None:
        self.assertEqual(self.run_guard("protect").returncode, 0)
        self.arm_candidate()

        result = self.run_guard("protect")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("still active", result.stderr)

    def test_router_wrapper_dispatches_all_guard_operations(self) -> None:
        wrapper = (ROOT / "scripts/router-local-test.sh").read_text(encoding="utf-8")
        self.assertIn('"$router_backup_dir" protect', wrapper)
        self.assertIn('"$router_backup_dir" arm "$remote_stage_dir"', wrapper)
        self.assertIn('"$router_backup_dir" check', wrapper)
        self.assertIn('"$router_backup_dir" restore', wrapper)

    def test_wrapper_arms_exact_candidate_before_any_live_copy(self) -> None:
        wrapper = (ROOT / "scripts/router-local-test.sh").read_text(encoding="utf-8")
        stage_body = wrapper.split("stage_candidate() {", 1)[1].split("\ncheck_router() {", 1)[0]
        self.assertLess(stage_body.index("arm_router_stage"), stage_body.index("install_candidate passwall2"))
        self.assertIn('mktemp "\\$destination.xray-mitm-stage.XXXXXX"', stage_body)
        self.assertIn('mv -f "\\$temporary_file" "\\$destination"', stage_body)

    def test_restore_replaces_files_atomically(self) -> None:
        guard = GUARD.read_text(encoding="utf-8")
        self.assertIn('mktemp "$destination_file.xray-mitm-restore.XXXXXX"', guard)
        self.assertIn('mv -f "$temporary_file" "$destination_file"', guard)


if __name__ == "__main__":
    unittest.main()
