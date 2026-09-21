#!/bin/sh
set -eu

die() {
	printf 'ERROR: %s\n' "$*" >&2
	exit 1
}

index_file=${1:-}
key_file=${2:-}
apk_bin=${APK_BIN:-apk}

[ -n "$index_file" ] || die 'APK index path is required.'
[ -n "$key_file" ] || die 'APK private-key path is required.'
[ -f "$index_file" ] || die "APK index does not exist: $index_file"
[ -f "$key_file" ] || die "APK private key does not exist: $key_file"
[ "$(stat -c '%a' "$key_file" 2>/dev/null || stat -f '%Lp' "$key_file")" = '600' ] || \
	die 'APK private key must have mode 0600.'

if ! command -v "$apk_bin" >/dev/null 2>&1 && [ ! -x "$apk_bin" ]; then
	die "apk executable is unavailable: $apk_bin"
fi

"$apk_bin" adbsign --sign-key "$key_file" "$index_file"
printf '%s\n' 'APK index signed.'
