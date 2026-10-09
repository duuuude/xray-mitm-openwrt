#!/usr/bin/env python3
"""Synthetic metadata only: no router, credentials, package install or signing."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/apk-config-delta.py"
spec = importlib.util.spec_from_file_location("apk_config_delta", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ConfigDeltaTests(unittest.TestCase):
    def setUp(self):
        active = dict(kind="regular", sha256="a" * 64, size=200, uid=0, gid=0, mode="0600")
        self.new = dict(kind="regular", sha256="b" * 64, size=155, uid=0, gid=0, mode="0600")
        self.snapshot = dict(config_path="/etc/config/xray-mitm", candidate_sha="c" * 40,
                             package_sha256="d" * 64, package_default=dict(sha256="b" * 64, size=155),
                             active_before=active, active_after=copy.deepcopy(active),
                             apk_new_before=None, apk_new_after=self.new, other_config_deltas=[])

    def state(self, phase="upgrade"):
        out = module.classify(self.snapshot, phase)
        self.assertEqual(out["live_validation"], "UNPROVEN")
        self.assertEqual(out["mutation_authority"], "NONE")
        return out["config_delta"]

    def test_exact_new_default_allowed_only_for_upgrade(self):
        self.assertEqual(self.state(), "EXPECTED_APK_NEW")
        self.assertEqual(self.state("rollback"), "HOLD")

    def test_absent_and_unchanged_existing_baselines(self):
        for value in (None, self.new):
            self.snapshot.update(apk_new_before=value, apk_new_after=copy.deepcopy(value))
            self.assertEqual(self.state(), "UNCHANGED")
            self.assertEqual(self.state("rollback"), "UNCHANGED")

    def test_preexisting_file_not_replaceable(self):
        self.snapshot["apk_new_before"] = {**self.new, "sha256": "e" * 64}
        self.assertEqual(self.state(), "HOLD")

    def test_preexisting_file_not_removable(self):
        self.snapshot.update(apk_new_before=self.new, apk_new_after=None)
        self.assertEqual(self.state(), "HOLD")

    def test_default_hash_size_owner_mode_and_type_mismatches(self):
        for key, value in (("sha256", "e" * 64), ("size", 154), ("uid", 1),
                           ("gid", 1), ("mode", "0644"), ("kind", "symlink")):
            with self.subTest(key=key):
                self.snapshot["apk_new_after"] = {**self.new, key: value}
                self.assertEqual(self.state(), "HOLD")

    def test_active_config_metadata_preserved(self):
        for key, value in (("sha256", "e" * 64), ("size", 201), ("uid", 1),
                           ("gid", 1), ("mode", "0644"), ("kind", "symlink")):
            with self.subTest(key=key):
                self.snapshot["active_after"] = {**self.snapshot["active_before"], key: value}
                self.assertEqual(self.state(), "HOLD")

    def test_other_changes_and_missing_inventory_block(self):
        for value in (["/etc/config/firewall"], None, {}, ""):
            self.snapshot["other_config_deltas"] = value
            self.assertEqual(self.state(), "HOLD")

    def test_wrong_path_or_unbound_candidate_blocks(self):
        for key, value in (("config_path", "/etc/config/firewall"), ("candidate_sha", ""),
                           ("package_sha256", "")):
            with self.subTest(key=key):
                snapshot = copy.deepcopy(self.snapshot)
                snapshot[key] = value
                self.assertEqual(module.classify(snapshot, "upgrade")["config_delta"], "HOLD")

    def test_missing_extra_and_malformed_metadata_block(self):
        for snapshot in (None, {}, {**self.snapshot, "extra": True},
                         {**self.snapshot, "active_after": None},
                         {**self.snapshot, "package_default": {"sha256": "b" * 64, "size": True}}):
            self.assertEqual(module.classify(snapshot, "upgrade")["config_delta"], "HOLD")

    def test_boolean_metadata_not_integer(self):
        self.snapshot["apk_new_after"] = {**self.new, "uid": False}
        self.assertEqual(self.state(), "HOLD")

    def test_cli_fail_closed_and_never_echoes_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.json"
            for text, code in ((json.dumps(self.snapshot), 0), ('{"secret":"DO_NOT_ECHO"}', 1),
                               ('{"x":1,"x":2}', 1), ("x" * 4097, 1)):
                path.write_text(text)
                result = subprocess.run(["python3", str(SCRIPT), "--phase", "upgrade",
                                         "--snapshot", str(path)], capture_output=True, text=True)
                self.assertEqual(result.returncode, code)
                self.assertNotIn("DO_NOT_ECHO", result.stdout + result.stderr)
                self.assertEqual(json.loads(result.stdout)["live_validation"], "UNPROVEN")


if __name__ == "__main__":
    unittest.main()
