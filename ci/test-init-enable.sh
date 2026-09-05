#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)
test_root=$(mktemp -d "${TMPDIR:-/tmp}/xray-mitm-init-test.XXXXXX")

cleanup() {
	rm -rf "$test_root"
}
trap cleanup EXIT HUP INT TERM

mkdir -p "$test_root/etc/rc.d"

TEST_INIT_ROOT="$test_root" \
	TEST_INIT_SCRIPT="$project_dir/xray-mitm/files/etc/init.d/xray-mitm" \
	sh -eu <<'EOF'
config_load() { :; }
config_get_bool() { boot_enabled="$TEST_BOOT_ENABLED"; }
disable() {
	rm -f "$IPKG_INSTROOT"/etc/rc.d/S??xray-mitm
	rm -f "$IPKG_INSTROOT"/etc/rc.d/K??xray-mitm
}

initscript=/etc/init.d/xray-mitm
IPKG_INSTROOT=$TEST_INIT_ROOT
TEST_BOOT_ENABLED=0

. "$TEST_INIT_SCRIPT"

enable
[ ! -e "$IPKG_INSTROOT/etc/rc.d/S98xray-mitm" ]
[ ! -e "$IPKG_INSTROOT/etc/rc.d/K10xray-mitm" ]

TEST_BOOT_ENABLED=1
enable
[ "$(readlink "$IPKG_INSTROOT/etc/rc.d/S98xray-mitm")" = ../init.d/xray-mitm ]
[ "$(readlink "$IPKG_INSTROOT/etc/rc.d/K10xray-mitm")" = ../init.d/xray-mitm ]

TEST_BOOT_ENABLED=0
enable
[ ! -e "$IPKG_INSTROOT/etc/rc.d/S98xray-mitm" ]
[ ! -e "$IPKG_INSTROOT/etc/rc.d/K10xray-mitm" ]

# A failure to create the second link must not leave the first link behind.
mkdir "$IPKG_INSTROOT/etc/rc.d/K10xray-mitm"
TEST_BOOT_ENABLED=1
if enable 2>/dev/null; then
	printf '%s\n' 'enable unexpectedly succeeded with an obstructed stop link' >&2
	exit 1
fi
[ ! -e "$IPKG_INSTROOT/etc/rc.d/S98xray-mitm" ]
rmdir "$IPKG_INSTROOT/etc/rc.d/K10xray-mitm"
EOF

printf '%s\n' 'Init enable guard passed disabled, explicit-enable, and failure-cleanup tests.'
