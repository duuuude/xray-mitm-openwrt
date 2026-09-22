"""Validate the bounded router DNS fallback assets without router access."""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "scripts" / "router-dns-fallback"


class RouterDnsFallbackTests(unittest.TestCase):
    def test_config_is_bounded_to_local_dns_listener(self) -> None:
        config = json.loads((ASSET_DIR / "xray-config.json").read_text())
        self.assertEqual(config["inbounds"], [
            {
                "tag": "dns-in",
                "listen": "127.0.0.1",
                "port": 2005,
                "protocol": "dokodemo-door",
                "settings": {
                    "address": "1.1.1.1",
                    "port": 53,
                    "network": "tcp,udp",
                    "followRedirect": False,
                },
            }
        ])
        self.assertEqual(config["outbounds"], [{
            "tag": "dns-out",
            "protocol": "dns",
            "settings": {"nonIPQuery": "skip"},
        }])
        self.assertEqual(config["routing"]["rules"][0]["outboundTag"], "dns-out")

    def test_assets_are_syntax_valid(self) -> None:
        for path in (
            ROOT / "scripts" / "router-dns-fallback.sh",
            ASSET_DIR / "init.d-xray-mitm-dns",
        ):
            result = subprocess.run(
                ["sh", "-n", str(path)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_remove_refuses_to_leave_dnsmasq_without_a_listener(self) -> None:
        script = (ROOT / "scripts" / "router-dns-fallback.sh").read_text()
        self.assertIn(
            "dnsmasq_config=$(uci -q show dhcp.@dnsmasq[0]) || {",
            script,
        )
        self.assertIn(
            "grep -Eq '\\.server=.*127\\.0\\.0\\.1#2005'",
            script,
        )
        self.assertIn("uci_changes_clean", script)
        self.assertIn(
            "if ! uci_changes_output=$(uci changes 2>/dev/null); then",
            script,
        )
        self.assertNotIn("uci changes | wc -l | tr -d ' '", script)

    def test_dns_gate_retries_and_uses_stable_domains(self) -> None:
        script = (ROOT / "scripts" / "router-dns-fallback.sh").read_text()
        self.assertGreaterEqual(script.count("dns_lookup_ok()"), 2)
        self.assertIn('while [ "$attempt" -le 3 ]; do', script)
        self.assertIn('timeout 4 nslookup "$name" 127.0.0.1', script)
        self.assertEqual(script.count('grep -Fqx "$name"'), 2)
        self.assertNotIn('grep -Fq "Name: $name"', script)
        self.assertIn("printf 'dns_example='", script)
        self.assertIn("printf 'dns_iana='", script)
        self.assertIn("printf 'dns_checks='", script)
        self.assertIn("for name in openwrt.org iana.org; do", script)
        self.assertNotIn("for name in example.com openwrt.org; do", script)

    def test_dns_name_match_rejects_non_exact_nslookup_names(self) -> None:
        script = (ROOT / "scripts" / "router-dns-fallback.sh").read_text()
        functions = re.findall(
            r"(?ms)^dns_lookup_ok\(\) \{\n.*?^\}\n", script
        )
        self.assertEqual(len(functions), 2)

        with tempfile.TemporaryDirectory() as temp_dir:
            bin_dir = pathlib.Path(temp_dir) / "bin"
            bin_dir.mkdir()
            (bin_dir / "timeout").write_text("#!/bin/sh\nshift\nexec \"$@\"\n")
            (bin_dir / "nslookup").write_text(
                "#!/bin/sh\ncat \"$DNS_OUTPUT\"\n"
            )
            (bin_dir / "sleep").write_text("#!/bin/sh\nexit 0\n")
            for path in bin_dir.iterdir():
                path.chmod(0o755)

            env = os.environ.copy()
            env["PATH"] = f"{bin_dir}:{env['PATH']}"
            output_path = pathlib.Path(temp_dir) / "nslookup.out"
            env["DNS_OUTPUT"] = str(output_path)

            def run_lookup(output: str) -> subprocess.CompletedProcess[str]:
                output_path.write_text(output)
                return subprocess.run(
                    ["sh", "-c", f"{functions[0]}\ndns_lookup_ok openwrt.org"],
                    check=False,
                    capture_output=True,
                    text=True,
                    env=env,
                )

            self.assertEqual(
                run_lookup("Name: openwrt.org  \nAddress: 192.0.2.1\n").returncode,
                0,
            )
            for impostor in (
                "Name: openwrt.org.evil\nAddress: 192.0.2.1\n",
                "Name: evil.openwrt.org\nAddress: 192.0.2.1\n",
                "Answer contains openwrt.org\nAddress: 192.0.2.1\n",
            ):
                self.assertNotEqual(run_lookup(impostor).returncode, 0)

    def test_rollback_preserves_helper_when_cleanup_fails(self) -> None:
        script = (ROOT / "scripts" / "router-dns-fallback.sh").read_text()
        self.assertIn("rollback_ok=1", script)
        self.assertIn(
            'if "$init_target" disable >/dev/null 2>&1; then :; else rollback_ok=0; fi',
            script,
        )
        self.assertIn(
            'if "$init_target" stop >/dev/null 2>&1; then :; else rollback_ok=0; fi',
            script,
        )
        self.assertIn("if listener_state_value=$(listener_state); then", script)
        self.assertIn("rollback_ok=0", script)
        self.assertIn('if [ "$rollback_ok" -eq 1 ]; then', script)

    def test_uci_and_listener_inspection_fail_closed(self) -> None:
        script = (ROOT / "scripts" / "router-dns-fallback.sh").read_text()
        uci_functions = re.findall(
            r"(?ms)^uci_changes_clean\(\) \{\n.*?^\}\n", script
        )
        listener_functions = re.findall(
            r"(?ms)^listener_state\(\) \{\n.*?^\}\n", script
        )
        self.assertEqual(len(uci_functions), 2)
        self.assertEqual(len(listener_functions), 3)

        with tempfile.TemporaryDirectory() as temp_dir:
            bin_dir = pathlib.Path(temp_dir) / "bin"
            bin_dir.mkdir()
            (bin_dir / "uci").write_text(
                """#!/bin/sh
if [ "$1" = changes ]; then
    case "$UCI_MODE" in
        fail) exit 1 ;;
        pending) printf '%s\\n' pending-change ;;
    esac
fi
"""
            )
            listener_command = """#!/bin/sh
case "$LISTENER_MODE" in
    present) printf '%s\\n' 'LISTEN 0 128 127.0.0.1:2005 0.0.0.0:*' ;;
    present_ipv6_bracketed) printf '%s\\n' 'LISTEN 0 128 [::1]:2005 [::]:*' ;;
    present_ipv6_plain) printf '%s\\n' 'LISTEN 0 128 ::1:2005 :::*' ;;
    impostor_port_suffix) printf '%s\\n' 'LISTEN 0 128 127.0.0.1:20050 0.0.0.0:*' ;;
    impostor_address_suffix) printf '%s\\n' 'LISTEN 0 128 127.0.0.10:2005 0.0.0.0:*' ;;
    absent) : ;;
    fail) exit 1 ;;
esac
"""
            (bin_dir / "ss").write_text(listener_command)
            (bin_dir / "netstat").write_text(listener_command)
            for path in bin_dir.iterdir():
                path.chmod(0o755)

            env = os.environ.copy()
            env["PATH"] = f"{bin_dir}:{env['PATH']}"

            def run_function(
                function: str,
                invocation: str,
                **updates: str,
            ) -> subprocess.CompletedProcess:
                trial_env = env.copy()
                trial_env.update(updates)
                return subprocess.run(
                    ["sh", "-c", f"{function}\n{invocation}"],
                    check=False,
                    capture_output=True,
                    text=True,
                    env=trial_env,
                )

            for function in uci_functions:
                self.assertNotEqual(
                    run_function(function, "uci_changes_clean", UCI_MODE="fail").returncode,
                    0,
                )
                self.assertNotEqual(
                    run_function(
                        function,
                        "uci_changes_clean",
                        UCI_MODE="pending",
                    ).returncode,
                    0,
                )
                self.assertEqual(
                    run_function(function, "uci_changes_clean", UCI_MODE="clean").returncode,
                    0,
                )

            for function in listener_functions:
                present = run_function(
                    function,
                    "listener_state",
                    LISTENER_MODE="present",
                )
                self.assertEqual(present.returncode, 0)
                self.assertEqual(present.stdout, "present\n")

                for ipv6_mode in ("present_ipv6_bracketed", "present_ipv6_plain"):
                    ipv6_present = run_function(
                        function,
                        "listener_state",
                        LISTENER_MODE=ipv6_mode,
                    )
                    self.assertEqual(ipv6_present.returncode, 0)
                    self.assertEqual(ipv6_present.stdout, "present\n")

                for impostor_mode in ("impostor_port_suffix", "impostor_address_suffix"):
                    impostor = run_function(
                        function,
                        "listener_state",
                        LISTENER_MODE=impostor_mode,
                    )
                    self.assertEqual(impostor.returncode, 0)
                    self.assertEqual(impostor.stdout, "absent\n")

                absent = run_function(
                    function,
                    "listener_state",
                    LISTENER_MODE="absent",
                )
                self.assertEqual(absent.returncode, 0)
                self.assertEqual(absent.stdout, "absent\n")

                failed = run_function(
                    function,
                    "listener_state",
                    LISTENER_MODE="fail",
                )
                self.assertNotEqual(failed.returncode, 0)
                self.assertEqual(failed.stdout, "unknown\n")

    def test_remove_verifies_listener_absence_before_deleting_owned_files(self) -> None:
        script = (ROOT / "scripts" / "router-dns-fallback.sh").read_text()
        remove_body = re.search(
            r"(?ms)remove_fallback\(\) \{\n\tssh_router sh -s <<'REMOTE'\n(.*?)\nREMOTE",
            script,
        )
        self.assertIsNotNone(remove_body)
        body = remove_body.group(1)
        self.assertIn("uci_changes_clean", body)
        self.assertIn("removal_ok=1", body)
        self.assertIn("if listener_state_value=$(listener_state); then", body)
        self.assertIn('if [ "$listener_state_value" = absent ]; then', body)
        self.assertIn(
            "router_dns_fallback: refusing removal until DNS listener absence is verified",
            body,
        )
        self.assertLess(
            body.index("if [ \"$removal_ok\" -ne 1 ] || [ \"$i\" -ge 10 ]; then"),
            body.index("rm -f /etc/xray-mitm/dns-proxy.json"),
        )

    def test_local_hashing_supports_macos_and_linux_tools(self) -> None:
        script = (ROOT / "scripts" / "router-dns-fallback.sh").read_text()
        self.assertIn("shasum -a 256", script)
        self.assertIn("sha256sum", script)

    def test_script_does_not_contain_secret_bearing_fields(self) -> None:
        contents = "\n".join(
            path.read_text()
            for path in (
                ROOT / "scripts" / "router-dns-fallback.sh",
                ASSET_DIR / "xray-config.json",
                ASSET_DIR / "init.d-xray-mitm-dns",
            )
        )
        for forbidden in ("password", "privateKey", "uuid", "subscription"):
            self.assertNotIn(forbidden, contents)


if __name__ == "__main__":
    unittest.main()
