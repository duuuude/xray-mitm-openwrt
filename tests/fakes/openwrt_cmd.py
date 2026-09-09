#!/usr/bin/env python3
"""Small OpenWrt command fixture used only by the offline test suite.

The real package continues to use the router's uci, jsonfilter, stat, flock,
and apk commands.  Tests copy this file under those command names in a private
temporary PATH so no host or router state is touched.
"""

from __future__ import annotations

import json
import os
import shlex
import stat as stat_module
import sys
from pathlib import Path


def fail(message: str | None = None) -> int:
    if message:
        print(message, file=sys.stderr)
    return 1


def quote_uci(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def load_uci(path: Path) -> list[dict[str, object]]:
    try:
        lexer = shlex.shlex(path.read_text(encoding="utf-8"), posix=True)
    except OSError:
        raise ValueError("configuration not found")
    lexer.whitespace_split = True
    lexer.commenters = "#"
    tokens = list(lexer)
    sections: list[dict[str, object]] = []
    index = 0
    while index < len(tokens):
        directive = tokens[index]
        index += 1
        if directive == "config":
            if index + 1 >= len(tokens):
                raise ValueError("truncated config directive")
            section_type, name = tokens[index : index + 2]
            index += 2
            sections.append({"type": section_type, "name": name, "options": {}})
        elif directive in {"option", "list"}:
            if not sections or index + 1 >= len(tokens):
                raise ValueError("truncated option directive")
            key, value = tokens[index : index + 2]
            index += 2
            options = sections[-1]["options"]
            assert isinstance(options, dict)
            if directive == "list":
                existing = options.get(key)
                if not isinstance(existing, list):
                    existing = []
                    options[key] = existing
                existing.append(value)
            else:
                options[key] = value
        else:
            raise ValueError(f"unsupported UCI directive: {directive}")
    return sections


def save_uci(path: Path, sections: list[dict[str, object]]) -> None:
    lines: list[str] = []
    for section in sections:
        lines.append(
            f"config {section['type']} {quote_uci(str(section['name']))}"
        )
        options = section["options"]
        assert isinstance(options, dict)
        for key, value in options.items():
            if isinstance(value, list):
                for item in value:
                    lines.append(f"\tlist {key} {quote_uci(str(item))}")
            else:
                lines.append(f"\toption {key} {quote_uci(str(value))}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    path.chmod(0o600)


def resolve_section(
    sections: list[dict[str, object]], selector: str
) -> dict[str, object] | None:
    if selector.startswith("@") and selector.endswith("]") and "[" in selector:
        section_type, raw_index = selector[1:-1].split("[", 1)
        try:
            wanted_index = int(raw_index)
        except ValueError:
            return None
        matches = [item for item in sections if item["type"] == section_type]
        if wanted_index < 0:
            wanted_index += len(matches)
        return matches[wanted_index] if 0 <= wanted_index < len(matches) else None
    for section in sections:
        if section["name"] == selector:
            return section
    return None


def parse_reference(reference: str) -> tuple[str, str, str | None] | None:
    parts = reference.split(".", 2)
    if len(parts) < 2 or parts[0] not in {"passwall2", "xray-mitm"}:
        return None
    return parts[0], parts[1], parts[2] if len(parts) == 3 else None


def uci_main(argv: list[str]) -> int:
    config_dir: Path | None = None
    saved_dir: Path | None = None
    no_commit = False
    index = 0
    while index < len(argv) and argv[index].startswith("-"):
        option = argv[index]
        index += 1
        if option in {"-c", "-P", "-t"}:
            if index >= len(argv):
                return fail()
            if option == "-c":
                config_dir = Path(argv[index])
            else:
                saved_dir = Path(argv[index])
                no_commit = option == "-P"
            index += 1
        elif option == "-q":
            continue
        else:
            return fail(f"unsupported fake uci option: {option}")
    if config_dir is None:
        test_root = os.environ.get("XRAY_MITM_TEST_ROOT")
        if not test_root:
            return fail()
        config_dir = Path(test_root) / "etc/config"
    if index >= len(argv):
        return fail()
    action = argv[index]
    operands = argv[index + 1 :]

    def package_path(package: str, mutating: bool = False) -> Path:
        source = config_dir / package
        if saved_dir is None:
            return source
        overlay = saved_dir / package
        if overlay.exists():
            return overlay
        if mutating:
            saved_dir.mkdir(parents=True, exist_ok=True)
            overlay.write_bytes(source.read_bytes())
            overlay.chmod(0o600)
            return overlay
        return source

    if action == "changes":
        if len(operands) != 1:
            return fail()
        marker = config_dir / f".pending-{operands[0]}"
        if marker.exists():
            print(f"{operands[0]}.fixture='pending'")
        return 0

    if action == "show":
        if len(operands) != 1 or operands[0] not in {"passwall2", "xray-mitm"}:
            return fail()
        package = operands[0]
        try:
            sections = load_uci(package_path(package))
        except ValueError:
            return fail()
        for section in sections:
            print(f"{package}.{section['name']}={section['type']}")
        return 0

    if action == "get":
        if len(operands) != 1:
            return fail()
        parsed = parse_reference(operands[0])
        if parsed is None:
            return fail()
        package, selector, option = parsed
        try:
            sections = load_uci(package_path(package))
        except ValueError:
            return fail()
        section = resolve_section(sections, selector)
        if section is None:
            return fail()
        if option is None:
            print(section["type"])
            return 0
        options = section["options"]
        assert isinstance(options, dict)
        if option not in options:
            return fail()
        value = options[option]
        if isinstance(value, list):
            print(" ".join(str(item) for item in value))
        else:
            print(value)
        return 0

    if action == "commit":
        if len(operands) != 1 or operands[0] not in {"passwall2", "xray-mitm"}:
            return fail()
        if no_commit or saved_dir is None:
            return 0
        overlay = saved_dir / operands[0]
        if overlay.exists():
            (config_dir / operands[0]).write_bytes(overlay.read_bytes())
            (config_dir / operands[0]).chmod(0o600)
            overlay.unlink()
        return 0

    if len(operands) != 1:
        return fail()

    if action == "set":
        if "=" not in operands[0]:
            return fail()
        reference, value = operands[0].split("=", 1)
        parsed = parse_reference(reference)
        if parsed is None:
            return fail()
        package, selector, option = parsed
        target_path = package_path(package, mutating=True)
        try:
            sections = load_uci(target_path)
        except ValueError:
            return fail()
        section = resolve_section(sections, selector)
        if option is None:
            if section is None:
                sections.append({"type": value, "name": selector, "options": {}})
            else:
                section["type"] = value
        else:
            if section is None:
                return fail()
            options = section["options"]
            assert isinstance(options, dict)
            options[option] = value
        save_uci(target_path, sections)
        return 0

    if action == "delete":
        parsed = parse_reference(operands[0])
        if parsed is None:
            return fail()
        package, selector, option = parsed
        target_path = package_path(package, mutating=True)
        try:
            sections = load_uci(target_path)
        except ValueError:
            return fail()
        section = resolve_section(sections, selector)
        if section is None:
            return fail()
        if option is None:
            sections.remove(section)
        else:
            options = section["options"]
            assert isinstance(options, dict)
            if option not in options:
                return fail()
            del options[option]
        save_uci(target_path, sections)
        return 0

    if action == "reorder":
        if "=" not in operands[0]:
            return fail()
        reference, raw_position = operands[0].split("=", 1)
        parsed = parse_reference(reference)
        if parsed is None or parsed[2] is not None:
            return fail()
        target_path = package_path(parsed[0], mutating=True)
        try:
            sections = load_uci(target_path)
        except ValueError:
            return fail()
        section = resolve_section(sections, parsed[1])
        try:
            position = int(raw_position)
        except ValueError:
            return fail()
        if section is None or position < 0 or position >= len(sections):
            return fail()
        sections.remove(section)
        sections.insert(position, section)
        save_uci(target_path, sections)
        return 0

    return fail(f"unsupported fake uci action: {action}")


def jsonfilter_main(argv: list[str]) -> int:
    try:
        input_path = Path(argv[argv.index("-i") + 1])
        expression = argv[argv.index("-e") + 1]
        data = json.loads(input_path.read_text(encoding="utf-8"))
    except (ValueError, IndexError, OSError, json.JSONDecodeError):
        return fail()
    if not expression.startswith("@."):
        return fail()
    value = data.get(expression[2:])
    if value is None:
        return 0
    if isinstance(value, bool):
        print("true" if value else "false")
    elif isinstance(value, (str, int, float)):
        print(value)
    else:
        print(json.dumps(value, separators=(",", ":")))
    return 0


def stat_main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[0] != "-c":
        return fail()
    try:
        details = os.stat(argv[2], follow_symlinks=True)
    except OSError:
        return fail()
    # The production RPC creates request files as uid 0. The fixture itself
    # normally runs as an unprivileged host user, so emulate only that narrow
    # ownership fact for the private request namespace.
    request_prefix = os.environ.get("XRAY_MITM_TEST_ROOT", "") + "/tmp/xray-mitm-plan."
    import_prefix = "/tmp/xray-mitm-rpc."
    reported_uid = 0 if argv[2].startswith((request_prefix, import_prefix)) else details.st_uid
    values = {
        "%u": str(reported_uid),
        "%a": format(stat_module.S_IMODE(details.st_mode), "o"),
        "%s": str(details.st_size),
        "%h": str(details.st_nlink),
    }
    output = argv[1]
    for token, value in values.items():
        output = output.replace(token, value)
    print(output)
    return 0


def main() -> int:
    command = Path(sys.argv[0]).name
    if command == "uci":
        return uci_main(sys.argv[1:])
    if command == "jsonfilter":
        return jsonfilter_main(sys.argv[1:])
    if command == "stat":
        return stat_main(sys.argv[1:])
    if command in {"flock", "apk"}:
        return 0
    return fail(f"unsupported fixture command: {command}")


if __name__ == "__main__":
    raise SystemExit(main())
