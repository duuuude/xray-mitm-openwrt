#!/usr/bin/env python3
"""Offline release-safety and package-layout checks.

This intentionally uses only the Python standard library and never contacts a
router or the network.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path


EXCLUDED_DIRS = {
    ".git",
    ".idea",
    ".vscode",
    "__pycache__",
    "artifacts",
    "bin",
    "build_dir",
    "dist",
    "dl",
    "logs",
    "outputs",
    "staging_dir",
    "tmp",
    "work",
}

FORBIDDEN_NAME_PATTERNS = (
    re.compile(r"(?:^|/)__pycache__(?:/|$)", re.IGNORECASE),
    re.compile(r"\.(?:pyc|pyo)$", re.IGNORECASE),
    re.compile(r"(?:^|/)mycert\.(?:crt|key)$", re.IGNORECASE),
    re.compile(r"(?:^|/)(?:openwrt-)?working-backup\.tar\.gz$", re.IGNORECASE),
    re.compile(r"(?:^|/).*sysupgrade.*backup.*$", re.IGNORECASE),
    re.compile(r"(?:^|/)[^/]*backup[^/]*\.(?:tar(?:\.gz)?|tgz|zip)$", re.IGNORECASE),
    re.compile(r"(?:^|/)installed-packages(?:-with-versions)?\.txt$", re.IGNORECASE),
    re.compile(r"\.(?:apk|ipk|key|pem|crt|cer|p12|pfx|jks|keystore|kdbx)$", re.IGNORECASE),
    re.compile(r"(?:^|/)etc/(?:shadow|config/passwall2)$", re.IGNORECASE),
    re.compile(r"(?:^|/)dropbear_(?:rsa|ecdsa|ed25519)_host_key$", re.IGNORECASE),
    re.compile(r"(?:^|/)uhttpd\.key$", re.IGNORECASE),
)

PRIVATE_KEY_MARKER = re.compile(
    rb"(?m)^[ \t]*-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE" + rb" KEY-----[ \t]*$"
)

REQUIRED_PATHS = (
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    ".github/workflows/build.yml",
    ".github/workflows/publish-feed.yml",
    ".gitignore",
    "LICENSE",
    "README.md",
    "README.fa.md",
    "THIRD_PARTY_NOTICES.md",
    "ci/test-init-enable.sh",
    "docs/RELEASE_TESTING.md",
    "docs/SIGNED_FEED.md",
    "scripts/validate-release.sh",
    "install.sh",
    "keys/xray-mitm-feed-v1.pem",
    "scripts/check-release-version.sh",
    "scripts/release-notes.sh",
    "tests/fakes/openwrt_cmd.py",
    "tests/test_certificates.py",
    "tests/test_installer.py",
    "tests/test_passwall2.py",
    "tests/test_signed_feed.py",
    "xray-mitm/Makefile",
    "luci-app-xray-mitm/Makefile",
    "xray-mitm/files/etc/config/xray-mitm",
    "xray-mitm/files/etc/init.d/xray-mitm",
    "xray-mitm/files/usr/libexec/xray-mitm-check",
    "xray-mitm/files/usr/libexec/xray-mitm/cert",
    "xray-mitm/files/usr/libexec/xray-mitm/check",
    "xray-mitm/files/usr/libexec/xray-mitm/common.sh",
    "xray-mitm/files/usr/libexec/xray-mitm/config",
    "xray-mitm/files/usr/libexec/xray-mitm/passwall2",
    "xray-mitm/files/usr/sbin/xray-mitmctl",
    "xray-mitm/files/usr/share/xray-mitm/config.json.example",
    "luci-app-xray-mitm/htdocs/luci-static/resources/view/xray-mitm/overview.js",
    "luci-app-xray-mitm/root/usr/share/luci/menu.d/luci-app-xray-mitm.json",
    "luci-app-xray-mitm/root/usr/share/rpcd/acl.d/luci-app-xray-mitm.json",
    "luci-app-xray-mitm/root/usr/share/rpcd/ucode/xray-mitm.uc",
)

CORE_DEPENDENCIES = {
    "@USE_APK",
    "+xray-core",
    "+curl",
    "+openssl-util",
    "+uci",
    "+jsonfilter",
    "+coreutils-stat",
    "+v2ray-geoip",
    "+v2ray-geosite",
}

LUCI_DEPENDENCIES = {
    "@USE_APK",
    "+luci-base",
    "+xray-mitm",
    "+rpcd-mod-ucode",
    "+ucode-mod-fs",
}

EXPECTED_INBOUNDS = {
    ("mixed-in", "mixed", "127.0.0.1", 10808),
    ("tls-decrypt-h11", "tunnel", "127.0.0.1", 11666),
    ("tls-decrypt-h211", "tunnel", "127.0.0.1", 11777),
}

EXPECTED_XRAY_MINIMUM = "26.2.6"
EXPECTED_PROJECT_URL = "https://github.com/duuuude/xray-mitm-openwrt"
EXPECTED_FEED_KEY_SHA256 = (
    "3e0dc07ffef69d1512500b6add486381d8c261a8ec3fcce54fa403b35320df8a"
)
ALLOWED_PUBLIC_KEYS = {"keys/xray-mitm-feed-v1.pem"}

MUTATING_RPC_METHODS = {
    "runHealthCheck",
    "setupRecommended",
    "serviceAction",
    "installDefaultConfig",
    "generateCandidate",
    "importCandidate",
    "activateCandidate",
    "discardCandidate",
    "rollbackCertificate",
    "adoptLegacyCertificate",
    "recoverPassWall2",
    "planPassWall2",
    "applyPassWall2",
    "rollbackPassWall2",
}

READ_ONLY_RPC_METHODS = {
    "getStatus",
    "getSetupStatus",
    "getCertificateStatus",
    "exportCertificate",
    "inspectPassWall2",
}


def release_files(root: Path):
    # In CI, inspect exactly every tracked path, including a file that was
    # force-added below an otherwise ignored build/output directory.
    if (root / ".git").exists():
        result = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        if result.returncode == 0:
            for raw in result.stdout.split(b"\0"):
                if not raw:
                    continue
                path = root / os.fsdecode(raw)
                if path.is_file() or path.is_symlink():
                    yield path
            return

    for current, dirs, files in os.walk(root):
        current_path = Path(current)
        kept_dirs = []
        for name in sorted(dirs):
            path = current_path / name
            if path.is_symlink():
                yield path
            elif name not in EXCLUDED_DIRS:
                kept_dirs.append(name)
        dirs[:] = kept_dirs
        for name in sorted(files):
            yield current_path / name


def make_tokens(text: str, variable: str) -> set[str]:
    """Return exact whitespace-separated tokens from a one-line Make value."""
    match = re.search(
        rf"^[ \t]*{re.escape(variable)}[ \t]*:?=[ \t]*(.+?)[ \t]*$",
        text,
        re.MULTILINE,
    )
    return set(match.group(1).split()) if match else set()


def json_file(path: Path, errors: list[str]):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        errors.append(f"invalid JSON in {path.name}: {exc}")
        return None


def walk_json(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key, child
            yield from walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_json(child)


def check_sample_config(root: Path, errors: list[str]) -> None:
    relative = "xray-mitm/files/usr/share/xray-mitm/config.json.example"
    config = json_file(root / relative, errors)
    if not isinstance(config, dict):
        return

    inbounds = config.get("inbounds")
    if not isinstance(inbounds, list):
        errors.append(f"{relative} must contain an inbounds array")
    else:
        actual = {
            (
                item.get("tag"),
                item.get("protocol"),
                item.get("listen"),
                item.get("port"),
            )
            for item in inbounds
            if isinstance(item, dict)
        }
        if len(inbounds) != len(EXPECTED_INBOUNDS) or actual != EXPECTED_INBOUNDS:
            errors.append(
                f"{relative} must expose only the three fixed localhost listeners"
            )

    version = config.get("version")
    if not isinstance(version, dict) or version.get("min") != EXPECTED_XRAY_MINIMUM:
        errors.append(
            f"{relative} must require Xray {EXPECTED_XRAY_MINIMUM} or newer"
        )

    certificate_paths = []
    key_paths = []
    scalar_strings = []
    for key, value in walk_json(config):
        if key == "certificateFile":
            certificate_paths.append(value)
        elif key == "keyFile":
            key_paths.append(value)
        if isinstance(value, str):
            scalar_strings.append(value)
        elif isinstance(value, list):
            scalar_strings.extend(item for item in value if isinstance(item, str))

    if (
        not certificate_paths
        or not all(isinstance(path, str) for path in certificate_paths)
        or set(certificate_paths) != {"/etc/xray-mitm/mycert.crt"}
    ):
        errors.append(f"{relative} must use only /etc/xray-mitm/mycert.crt")
    if (
        not key_paths
        or not all(isinstance(path, str) for path in key_paths)
        or set(key_paths) != {"/etc/xray-mitm/mycert.key"}
    ):
        errors.append(f"{relative} must use only /etc/xray-mitm/mycert.key")
    if not any(value.startswith("geosite:") for value in scalar_strings):
        errors.append(f"{relative} does not reference the required geosite asset")
    if not any(value.startswith("geoip:") for value in scalar_strings):
        errors.append(f"{relative} does not reference the required geoip asset")


def check_safe_defaults(root: Path, errors: list[str]) -> None:
    relative = "xray-mitm/files/etc/config/xray-mitm"
    text = (root / relative).read_text(encoding="utf-8", errors="replace")
    if not re.search(r"^[ \t]*option enabled '0'[ \t]*$", text, re.MULTILINE):
        errors.append(f"{relative} must leave the service disabled")
    if not re.search(r"^[ \t]*option boot_enabled '0'[ \t]*$", text, re.MULTILINE):
        errors.append(f"{relative} must leave automatic startup disabled")
    if not re.search(r"^[ \t]*option provisioned '0'[ \t]*$", text, re.MULTILINE):
        errors.append(f"{relative} must leave certificate setup incomplete")
    if not re.search(
        r"^[ \t]*option asset_dir '/usr/share/v2ray'[ \t]*$", text, re.MULTILINE
    ):
        errors.append(f"{relative} must retain the official Xray asset directory")

    init_relative = "xray-mitm/files/etc/init.d/xray-mitm"
    init_text = (root / init_relative).read_text(encoding="utf-8", errors="replace")
    guarded_enable = re.search(
        r"^enable\(\)[ \t]*\{.*?"
        r"config_get_bool boot_enabled main boot_enabled 0.*?"
        r"\[ \"\$boot_enabled\" -eq 1 \] \|\| return 0",
        init_text,
        re.MULTILINE | re.DOTALL,
    )
    if not guarded_enable:
        errors.append(
            f"{init_relative} must block OpenWrt's implicit post-install boot enable"
        )

    for relative in ("xray-mitm/Makefile", "luci-app-xray-mitm/Makefile"):
        text = (root / relative).read_text(encoding="utf-8", errors="replace")
        if re.search(r"^define Package/.+/(?:preinst|postinst|prerm|postrm)$", text, re.MULTILINE):
            errors.append(f"{relative} must not mutate live state from package lifecycle scripts")


def check_acl(root: Path, errors: list[str]) -> None:
    relative = "luci-app-xray-mitm/root/usr/share/rpcd/acl.d/luci-app-xray-mitm.json"
    acl = json_file(root / relative, errors)
    if not isinstance(acl, dict):
        return
    entry = acl.get("luci-app-xray-mitm")
    if not isinstance(entry, dict):
        errors.append(f"{relative} is missing the package ACL entry")
        return

    read = entry.get("read")
    write = entry.get("write")
    if not isinstance(read, dict) or not isinstance(write, dict):
        errors.append(f"{relative} must declare read and write ACL objects")
        return
    read_ubus = read.get("ubus")
    write_ubus = write.get("ubus")
    if not isinstance(read_ubus, dict) or not isinstance(write_ubus, dict):
        errors.append(f"{relative} must declare narrow ubus ACL objects")
        return
    read_methods = read_ubus.get("luci.xray-mitm", [])
    write_methods = write_ubus.get("luci.xray-mitm", [])
    if (
        not isinstance(read_methods, list)
        or not isinstance(write_methods, list)
        or not all(isinstance(method, str) for method in read_methods + write_methods)
    ):
        errors.append(f"{relative} must declare explicit read and write RPC method arrays")
        return
    overlap = set(read_methods) & set(write_methods)
    if overlap:
        errors.append(f"{relative} duplicates RPC methods across read and write ACLs")
    missing = MUTATING_RPC_METHODS - set(write_methods)
    if missing:
        errors.append(f"{relative} lacks write-only methods: {', '.join(sorted(missing))}")
    if MUTATING_RPC_METHODS & set(read_methods):
        errors.append(f"{relative} grants mutating methods through the read ACL")
    if set(read_methods) != READ_ONLY_RPC_METHODS:
        errors.append(f"{relative} read ACL does not match the expected read-only methods")

    rpc_relative = "luci-app-xray-mitm/root/usr/share/rpcd/ucode/xray-mitm.uc"
    rpc_text = (root / rpc_relative).read_text(encoding="utf-8", errors="replace")
    declared_methods = set(
        re.findall(r"^\t([A-Za-z][A-Za-z0-9]*):[ \t]*\{$", rpc_text, re.MULTILINE)
    )
    expected_methods = READ_ONLY_RPC_METHODS | MUTATING_RPC_METHODS
    if declared_methods != expected_methods:
        errors.append(
            f"{rpc_relative} methods and {relative} grants must remain in exact sync"
        )

    serialized = json.dumps(acl, sort_keys=True)
    if '"*"' in serialized or '"file"' in serialized or '"cgi-io"' in serialized:
        errors.append(f"{relative} contains an overly broad file, CGI, or wildcard grant")


def check_workflow(root: Path, errors: list[str]) -> None:
    for relative in (
        ".github/workflows/build.yml",
        ".github/workflows/publish-feed.yml",
    ):
        text = (root / relative).read_text(encoding="utf-8", errors="replace")
        uses = re.findall(
            r"^[ \t]*(?:-[ \t]*)?uses:[ \t]*([^ #]+)", text, re.MULTILINE
        )
        if not uses:
            errors.append(f"{relative} does not invoke any actions")
        for action in uses:
            if not re.fullmatch(r"[^@\s]+@[0-9a-f]{40}", action):
                errors.append(
                    f"{relative} action is not pinned to a full commit: {action}"
                )

    relative = ".github/workflows/build.yml"
    text = (root / relative).read_text(encoding="utf-8", errors="replace")
    for required in (
        "install.sh",
        "PACKAGES",
        "SHA256SUMS",
        "LICENSE",
        "README.md",
        "README.fa.md",
        "THIRD_PARTY_NOTICES.md",
        "SOURCE_COMMIT",
    ):
        if required not in text:
            errors.append(f"{relative} release artifact does not mention {required}")
    if "pull_request_target:" in text:
        errors.append(f"{relative} must not execute package source through pull_request_target")
    if not re.search(r"^permissions:\s*\n[ \t]+contents:[ \t]*read[ \t]*$", text, re.MULTILINE):
        errors.append(f"{relative} must retain read-only repository permissions")
    if "${{ secrets." in text:
        errors.append(f"{relative} must not expose repository secrets to package builds")

    relative = ".github/workflows/publish-feed.yml"
    text = (root / relative).read_text(encoding="utf-8", errors="replace")
    for required in (
        "tags:",
        "environment: signed-feed",
        "secrets.XRAY_MITM_APK_PRIVATE_KEY",
        'INDEX: "1"',
        "packages.adb",
        "actions/upload-pages-artifact@",
        "actions/deploy-pages@",
        EXPECTED_FEED_KEY_SHA256,
    ):
        if required not in text:
            errors.append(f"{relative} signed publishing is missing {required}")
    for forbidden in ("pull_request:", "pull_request_target:", "workflow_dispatch:"):
        if forbidden in text:
            errors.append(f"{relative} must be tag-triggered only; found {forbidden}")
    if text.count("secrets.XRAY_MITM_APK_PRIVATE_KEY") != 2:
        errors.append(f"{relative} must use the signing secret only for key verification and signing")
    if "--allow-untrusted" in text:
        errors.append(f"{relative} must never bypass APK signature verification")


def check_signed_feed(root: Path, errors: list[str]) -> None:
    key_relative = "keys/xray-mitm-feed-v1.pem"
    key_payload = (root / key_relative).read_bytes()
    if b"-----BEGIN PUBLIC KEY-----" not in key_payload:
        errors.append(f"{key_relative} must contain a PEM public key")
    if b"PRIVATE KEY" in key_payload:
        errors.append(f"{key_relative} must never contain private-key material")

    key_digest = hashlib.sha256(key_payload).hexdigest()
    if key_digest != EXPECTED_FEED_KEY_SHA256:
        errors.append(f"{key_relative} does not match the reviewed public-key fingerprint")

    installer_relative = "install.sh"
    installer = (root / installer_relative).read_text(
        encoding="utf-8", errors="replace"
    )
    for required in (
        EXPECTED_FEED_KEY_SHA256,
        "https://duuuude.github.io/xray-mitm-openwrt/feed/25.12/all/packages.adb",
        "/etc/apk/keys",
        "/etc/apk/repositories.d",
        "apk add xray-mitm luci-app-xray-mitm",
        "apk upgrade xray-mitm luci-app-xray-mitm",
    ):
        if required not in installer:
            errors.append(f"{installer_relative} signed-feed logic is missing {required}")
    if re.search(r"apk[ \t]+(?:add|upgrade).*--allow-untrusted", installer):
        errors.append(f"{installer_relative} must not bypass APK signature verification")
    targeted_installer = installer.replace(
        "apk upgrade xray-mitm luci-app-xray-mitm", ""
    )
    if re.search(r"apk[ \t]+upgrade", targeted_installer):
        errors.append(f"{installer_relative} must not upgrade unrelated router packages")


def check_tree(root: Path) -> list[str]:
    errors: list[str] = []

    for relative in REQUIRED_PATHS:
        if not (root / relative).is_file():
            errors.append(f"missing required release file: {relative}")

    for path in release_files(root):
        relative = path.relative_to(root).as_posix()

        if path.is_symlink():
            errors.append(f"release tree must not contain symlinks: {relative}")
            continue

        if (
            relative not in ALLOWED_PUBLIC_KEYS
            and any(pattern.search(relative) for pattern in FORBIDDEN_NAME_PATTERNS)
        ):
            errors.append(f"forbidden release filename: {relative}")
            continue

        try:
            payload = path.read_bytes()
        except OSError as exc:
            errors.append(f"cannot read {relative}: {exc}")
            continue

        if PRIVATE_KEY_MARKER.search(payload):
            errors.append(f"private-key PEM content found: {relative}")

        if path.name.endswith((".json", ".json.example")):
            try:
                json.loads(payload.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                errors.append(f"invalid JSON in {relative}: {exc}")

    for relative in ("xray-mitm/Makefile", "luci-app-xray-mitm/Makefile"):
        path = root / relative
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        arch_text = text
        arch_variable = "LUCI_PKGARCH"
        if relative == "xray-mitm/Makefile":
            # Package/Default overwrites a top-level PKGARCH assignment.
            package = re.search(r"^define Package/xray-mitm\s*\n(.*?)^endef", text, re.MULTILINE | re.DOTALL)
            arch_text = package.group(1) if package else ""
            arch_variable = "PKGARCH"
        if not re.search(r"^[ \t]*" + arch_variable + r"\s*:?=\s*all\s*$", arch_text, re.MULTILINE):
            errors.append(f"{relative} must declare an architecture-independent package")

    core_makefile = root / "xray-mitm/Makefile"
    if core_makefile.is_file():
        text = core_makefile.read_text(encoding="utf-8", errors="replace")
        if f"URL:={EXPECTED_PROJECT_URL}" not in text:
            errors.append("xray-mitm/Makefile must identify the public source repository")
        if re.search(r"^PKG_SOURCE(?:_URL)?\s*:?=", text, re.MULTILINE):
            errors.append("xray-mitm contains local files only and must not request a source download")
        if "PKG_MAINTAINER:=duuuude" not in text:
            errors.append("xray-mitm/Makefile must identify the package maintainer")
        dependencies = make_tokens(text, "DEPENDS")
        missing = CORE_DEPENDENCIES - dependencies
        unexpected = dependencies - CORE_DEPENDENCIES
        if missing:
            errors.append(
                "xray-mitm/Makefile lacks exact dependencies: "
                + ", ".join(sorted(missing))
            )
        if unexpected:
            errors.append(
                "xray-mitm/Makefile has unreviewed dependencies: "
                + ", ".join(sorted(unexpected))
            )

    luci_makefile = root / "luci-app-xray-mitm/Makefile"
    if luci_makefile.is_file():
        text = luci_makefile.read_text(encoding="utf-8", errors="replace")
        if "PKG_MAINTAINER:=duuuude" not in text:
            errors.append("luci-app-xray-mitm/Makefile must identify the package maintainer")
        dependencies = make_tokens(text, "LUCI_DEPENDS")
        missing = LUCI_DEPENDENCIES - dependencies
        unexpected = dependencies - LUCI_DEPENDENCIES
        if missing:
            errors.append(
                "luci-app-xray-mitm/Makefile lacks exact dependencies: "
                + ", ".join(sorted(missing))
            )
        if unexpected:
            errors.append(
                "luci-app-xray-mitm/Makefile has unreviewed dependencies: "
                + ", ".join(sorted(unexpected))
            )

    if all((root / relative).is_file() for relative in REQUIRED_PATHS):
        check_sample_config(root, errors)
        check_safe_defaults(root, errors)
        check_acl(root, errors)
        check_workflow(root, errors)
        check_signed_feed(root, errors)

    return errors


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    errors = check_tree(root)
    if errors:
        print("Release validation failed:", file=sys.stderr)
        for error in errors:
            print(f" - {error}", file=sys.stderr)
        return 1

    print(
        "Release validation passed: layout, JSON and service invariants, exact "
        "dependencies, ACLs, pinned actions, noarch declarations, and secret checks are OK."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
