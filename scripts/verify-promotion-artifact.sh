#!/bin/sh
set -eu

die() {
	printf 'ERROR: %s\n' "$*" >&2
	exit 1
}

artifact_dir=${1:-}
expected_source=${2:-}
expected_release=${3:-}
expected_arch=${4:-}

[ -n "$artifact_dir" ] || die 'artifact directory is required.'
[ -d "$artifact_dir" ] || die "artifact directory does not exist: $artifact_dir"
[ -n "$expected_source" ] || die 'expected source commit is required.'
[ -n "$expected_release" ] || die 'expected OpenWrt release is required.'
[ -n "$expected_arch" ] || die 'expected SDK architecture is required.'

printf '%s\n' "$expected_source" | grep -Eq '^[0-9a-f]{40}$' || \
	die 'expected source commit is not a full lowercase SHA.'

for required in \
	SOURCE_COMMIT \
	OPENWRT_RELEASE \
	SDK_ARCH \
	PACKAGE_FORMAT \
	ARTIFACT_PURPOSE \
	PACKAGES \
	PACKAGE_SHA256SUMS \
	SHA256SUMS \
	packages.adb
do
	[ -f "$artifact_dir/$required" ] || die "artifact is missing $required."
done

test "$(cat "$artifact_dir/SOURCE_COMMIT")" = "$expected_source" || \
	die 'artifact source commit does not match the expected source.'
test "$(cat "$artifact_dir/OPENWRT_RELEASE")" = "$expected_release" || \
	die 'artifact OpenWrt release does not match the expected release.'
test "$(cat "$artifact_dir/SDK_ARCH")" = "$expected_arch" || \
	die 'artifact SDK architecture does not match the expected architecture.'
test "$(cat "$artifact_dir/PACKAGE_FORMAT")" = 'apk' || \
	die 'artifact package format is not apk.'
test "$(cat "$artifact_dir/ARTIFACT_PURPOSE")" = 'promotable unsigned APK bundle' || \
	die 'artifact purpose is not the promotable unsigned APK bundle.'

apk_count=$(find "$artifact_dir" -maxdepth 1 -type f -name '*.apk' | wc -l | tr -d ' ')
test "$apk_count" -eq 2 || die "expected exactly two APKs, found $apk_count."

set -- "$artifact_dir"/xray-mitm-*.apk
test "$#" -eq 1 && [ -f "$1" ] || die 'expected exactly one core APK.'
set -- "$artifact_dir"/luci-app-xray-mitm-*.apk
test "$#" -eq 1 && [ -f "$1" ] || die 'expected exactly one LuCI APK.'

actual_packages=$(find "$artifact_dir" -maxdepth 1 -type f -name '*.apk' -exec basename '{}' \; | LC_ALL=C sort)
declared_packages=$(LC_ALL=C sort "$artifact_dir/PACKAGES")
test "$actual_packages" = "$declared_packages" || \
	die 'PACKAGES does not exactly describe the APK files.'

declared_package_checksums=$(awk '{print $2}' "$artifact_dir/PACKAGE_SHA256SUMS" | LC_ALL=C sort)
test "$declared_package_checksums" = "$declared_packages" || \
	die 'PACKAGE_SHA256SUMS does not exactly describe the APK files.'

declared_all_checksums=$(awk '{print $2}' "$artifact_dir/SHA256SUMS" | LC_ALL=C sort)
expected_all_checksums=$(printf '%s\n%s\n' "$declared_packages" packages.adb | LC_ALL=C sort)
test "$declared_all_checksums" = "$expected_all_checksums" || \
	die 'SHA256SUMS does not exactly describe the APK files and packages.adb.'

(
	cd "$artifact_dir"
	sha256sum -c PACKAGE_SHA256SUMS
	sha256sum -c SHA256SUMS
)

printf '%s\n' 'Promotion artifact verified.'
