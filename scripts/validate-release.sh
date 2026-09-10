#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)

PYTHONDONTWRITEBYTECODE=1 python3 "$project_dir/ci/validate_release.py" "$project_dir"
PYTHONDONTWRITEBYTECODE=1 python3 "$project_dir/tests/test_passwall2.py"
PYTHONDONTWRITEBYTECODE=1 python3 "$project_dir/tests/test_certificates.py"
PYTHONDONTWRITEBYTECODE=1 python3 "$project_dir/tests/test_ctl.py"
PYTHONDONTWRITEBYTECODE=1 python3 "$project_dir/tests/test_installer.py"
PYTHONDONTWRITEBYTECODE=1 python3 "$project_dir/tests/test_signed_feed.py"
PYTHONDONTWRITEBYTECODE=1 python3 "$project_dir/tests/test_startup.py"

for relative in \
	xray-mitm/files/etc/init.d/xray-mitm \
	xray-mitm/files/usr/libexec/xray-mitm-check \
	xray-mitm/files/usr/libexec/xray-mitm/cert \
	xray-mitm/files/usr/libexec/xray-mitm/check \
	xray-mitm/files/usr/libexec/xray-mitm/common.sh \
	xray-mitm/files/usr/libexec/xray-mitm/config \
	xray-mitm/files/usr/libexec/xray-mitm/passwall2 \
	xray-mitm/files/usr/sbin/xray-mitmctl \
	install.sh \
	scripts/check-release-version.sh \
	scripts/release-notes.sh \
	ci/test-init-enable.sh
do
	sh -n "$project_dir/$relative"
done

sh "$project_dir/ci/test-init-enable.sh"

if command -v node >/dev/null 2>&1; then
	node --check "$project_dir/luci-app-xray-mitm/htdocs/luci-static/resources/view/xray-mitm/overview.js"
	printf '%s\n' 'Shell and LuCI JavaScript syntax checks passed.'
else
	printf '%s\n' 'Shell syntax checks passed; LuCI JavaScript syntax check skipped (Node.js not installed).'
fi
