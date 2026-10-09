#!/usr/bin/env python3
"""Read-only classification of supplied, secret-free APK conffile evidence.

This is not a signature verifier, evidence collector, or live-validation gate.
It never reads configuration contents or connects to a router.
"""
import argparse
import json
import re
from pathlib import Path


def exact_keys(value, keys):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError("invalid evidence fields")


def digest(value, length=64):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{%d}" % length, value):
        raise ValueError("invalid digest")


def metadata(value):
    exact_keys(value, ("kind", "sha256", "size", "uid", "gid", "mode"))
    if value["kind"] != "regular":
        raise ValueError("regular file required; symlinks are not allowed")
    digest(value["sha256"])
    for key in ("size", "uid", "gid"):
        if type(value[key]) is not int or value[key] < 0:
            raise ValueError("invalid file metadata")
    if not isinstance(value["mode"], str) or not re.fullmatch(r"0[0-7]{3}", value["mode"]):
        raise ValueError("invalid mode")


def classify(snapshot, phase, expected_candidate, expected_package):
    result = {"config_delta": "HOLD", "phase": phase,
              "live_validation": "UNPROVEN", "mutation_authority": "NONE"}
    try:
        digest(expected_candidate, 40)
        digest(expected_package)
        if phase not in ("upgrade", "rollback"):
            raise ValueError("invalid phase")
        exact_keys(snapshot, ("config_path", "candidate_sha", "package_sha256",
                              "package_default", "active_before", "active_after",
                              "apk_new_before", "apk_new_after", "other_config_deltas"))
        if snapshot["config_path"] != "/etc/config/xray-mitm":
            raise ValueError("unexpected path")
        digest(snapshot["candidate_sha"], 40)
        digest(snapshot["package_sha256"])
        if (snapshot["candidate_sha"] != expected_candidate
                or snapshot["package_sha256"] != expected_package):
            raise ValueError("snapshot identity mismatch")
        default = snapshot["package_default"]
        exact_keys(default, ("sha256", "size"))
        digest(default["sha256"])
        if type(default["size"]) is not int or default["size"] <= 0:
            raise ValueError("invalid default size")
        for key in ("active_before", "active_after"):
            metadata(snapshot[key])
        for key in ("apk_new_before", "apk_new_after"):
            if snapshot[key] is not None:
                metadata(snapshot[key])
        if snapshot["other_config_deltas"] != []:
            raise ValueError("unexplained or missing config delta inventory")
        if snapshot["active_before"] != snapshot["active_after"]:
            raise ValueError("active config changed")
        before, after = snapshot["apk_new_before"], snapshot["apk_new_after"]
        if before == after:
            result["config_delta"] = "UNCHANGED"
        elif phase == "upgrade" and before is None and after is not None:
            if (after["sha256"] != default["sha256"] or after["size"] != default["size"]
                    or (after["uid"], after["gid"], after["mode"]) != (0, 0, "0600")):
                raise ValueError("apk-new does not match the declared safe package default")
            result["config_delta"] = "EXPECTED_APK_NEW"
        else:
            raise ValueError("apk-new baseline differs; exact restoration not proven")
        result.update(candidate_sha=expected_candidate, package_sha256=expected_package)
    except (ValueError, TypeError, KeyError):
        # Do not echo supplied data: a malformed snapshot may contain secrets.
        result["config_delta"] = "HOLD"
    return result


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON field")
        value[key] = item
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("upgrade", "rollback"), required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--expected-candidate", required=True)
    parser.add_argument("--expected-package", required=True)
    args = parser.parse_args()
    try:
        with args.snapshot.open("rb") as handle:
            data = handle.read(4097)
        if len(data) > 4096:
            raise ValueError("oversized evidence")
        snapshot = json.loads(data, object_pairs_hook=unique_object)
    except (OSError, ValueError, UnicodeError):
        snapshot = None
    result = classify(snapshot, args.phase, args.expected_candidate, args.expected_package)
    print(json.dumps(result, sort_keys=True))
    return 1 if result["config_delta"] == "HOLD" else 0


if __name__ == "__main__":
    raise SystemExit(main())
