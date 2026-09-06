"""Exercise the production startup loops without a router or real sleeps."""
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "xray-mitm/files/usr/libexec/xray-mitm/cert").read_text()
FUNCTIONS = "\n".join(
    re.search(r"^" + name + r"\(\) \{\n.*?^\}", SOURCE, re.M | re.S).group()
    for name in ("restart_if_was_running", "restart_and_verify_if_was_running")
)


class StartupTests(unittest.TestCase):
    def run_case(self, running_after, healthy_after, expected):
        script = FUNCTIONS + f'''
XRAY_MITM_INIT=true
running_calls=0
health_calls=0
sleep_calls=0
sleep() {{ sleep_calls=$((sleep_calls + 1)); }}
xray_mitm_service_running() {{
    running_calls=$((running_calls + 1))
    [ "$running_calls" -ge {running_after} ]
}}
verify_running_mitm_path() {{
    health_calls=$((health_calls + 1))
    [ "$health_calls" -ge {healthy_after} ]
}}
restart_and_verify_if_was_running 1
result=$?
printf '%s %s %s %s' "$result" "$running_calls" "$health_calls" "$sleep_calls"
'''
        result = subprocess.run(["sh", "-c", script], text=True, capture_output=True, check=True)
        values = tuple(map(int, result.stdout.split()))
        self.assertEqual(values[0], expected)
        return values

    def test_slow_process_and_listener_eventually_pass(self):
        result = self.run_case(4, 5, 0)
        self.assertEqual(result[2], 5)
        self.assertEqual(result[3], 7)

    def test_process_never_starts_is_bounded(self):
        self.assertEqual(self.run_case(999, 1, 1), (1, 15, 0, 14))

    def test_health_never_passes_returns_failure_for_rollback(self):
        self.assertEqual(self.run_case(1, 999, 1), (1, 11, 10, 9))

    def test_temporary_config_has_explicit_format(self):
        source = (ROOT / "xray-mitm/files/usr/libexec/xray-mitm/config").read_text()
        self.assertIn('run -test -format=json -c "$file"', source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
