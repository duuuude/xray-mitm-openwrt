"""Validate the bounded router DNS fallback assets without router access."""

from __future__ import annotations

import json
import pathlib
import subprocess
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
        self.assertIn("test \"$(uci changes | wc -l | tr -d ' ')\" = 0", script)

    def test_dns_gate_retries_and_uses_stable_domains(self) -> None:
        script = (ROOT / "scripts" / "router-dns-fallback.sh").read_text()
        self.assertGreaterEqual(script.count("dns_lookup_ok()"), 2)
        self.assertIn('while [ "$attempt" -le 3 ]; do', script)
        self.assertIn('timeout 4 nslookup "$name" 127.0.0.1', script)
        self.assertIn("printf 'dns_example='", script)
        self.assertIn("printf 'dns_iana='", script)
        self.assertIn("printf 'dns_checks='", script)
        self.assertIn("for name in openwrt.org iana.org; do", script)
        self.assertNotIn("for name in example.com openwrt.org; do", script)

    def test_rollback_preserves_helper_when_cleanup_fails(self) -> None:
        script = (ROOT / "scripts" / "router-dns-fallback.sh").read_text()
        self.assertIn("rollback_ok=1", script)
        self.assertIn('"$init_target" disable >/dev/null 2>&1 || rollback_ok=0', script)
        self.assertIn('"$init_target" stop >/dev/null 2>&1 || rollback_ok=0', script)
        self.assertIn("if listener_present; then", script)
        self.assertIn('if [ "$rollback_ok" -eq 1 ]; then', script)

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
