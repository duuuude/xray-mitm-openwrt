#!/bin/sh
set -eu

PROJECT='duuuude/xray-mitm-openwrt'
FALLBACK_CORE_ASSET='xray-mitm-0.1.0-r4.apk'
FALLBACK_LUCI_ASSET='luci-app-xray-mitm-26.249.69617~5f96cdb.apk'
RELEASE="${XRAY_MITM_RELEASE:-latest}"
RELEASE_FILE="${XRAY_MITM_OPENWRT_RELEASE_FILE:-/etc/openwrt_release}"

say() {
	printf '%s\n' "$*"
}

die() {
	printf 'ERROR: %s\n' "$*" >&2
	exit 1
}

download() {
	url="$1"
	destination="$2"

	if command -v uclient-fetch >/dev/null 2>&1; then
		uclient-fetch -q -O "$destination" "$url"
	elif command -v wget >/dev/null 2>&1; then
		wget -q -O "$destination" "$url"
	elif command -v curl >/dev/null 2>&1; then
		curl -fL --retry 3 -o "$destination" "$url"
	else
		die 'No supported HTTPS downloader was found (uclient-fetch, wget, or curl).'
	fi
}

cleanup() {
	if [ -n "${work_dir:-}" ] && [ -d "$work_dir" ]; then
		rm -rf "$work_dir"
	fi
}

supported_openwrt_release() {
	version="${DISTRIB_RELEASE%%-*}"
	old_ifs="$IFS"
	IFS='.'
	set -- $version
	IFS="$old_ifs"
	major="${1:-0}"
	minor="${2:-0}"
	patch="${3:-0}"

	case "$major:$minor:$patch" in
		*[!0-9:]*) return 1 ;;
	esac

	[ "$major" -gt 25 ] ||
		{ [ "$major" -eq 25 ] && [ "$minor" -gt 12 ]; } ||
		{ [ "$major" -eq 25 ] && [ "$minor" -eq 12 ] && [ "$patch" -ge 5 ]; }
}

[ "$(id -u)" = '0' ] || die 'Run this installer as root on the OpenWrt router.'
[ -r "$RELEASE_FILE" ] || die 'This does not appear to be an OpenWrt router.'

# shellcheck disable=SC1090
. "$RELEASE_FILE"
[ -n "${DISTRIB_RELEASE:-}" ] || die 'OpenWrt release information is incomplete.'
command -v apk >/dev/null 2>&1 || die 'This release requires an APK-based OpenWrt installation (25.12.5 or later).'
command -v sha256sum >/dev/null 2>&1 || die 'sha256sum is required to verify the downloaded packages.'
supported_openwrt_release || die "OpenWrt $DISTRIB_RELEASE is unsupported; version 25.12.5 or later is required."

case "$RELEASE" in
	latest)
		base_url="https://github.com/$PROJECT/releases/latest/download"
		;;
	v[0-9]*.[0-9]*.[0-9]*)
		case "$RELEASE" in
			*[!A-Za-z0-9._-]*) die "Invalid release name: $RELEASE" ;;
		esac
		base_url="https://github.com/$PROJECT/releases/download/$RELEASE"
		;;
	*)
		die "Invalid release name: $RELEASE"
		;;
esac

if [ -n "${XRAY_MITM_BASE_URL:-}" ]; then
	base_url="${XRAY_MITM_BASE_URL%/}"
fi

umask 077
work_dir="$(mktemp -d "${TMPDIR:-/tmp}/xray-mitm-install.XXXXXX")"
trap cleanup EXIT HUP INT TERM

say "OpenWrt: $DISTRIB_RELEASE"
say "Release: $RELEASE"
say 'Downloading release files...'

cd "$work_dir"
if download "$base_url/PACKAGES" PACKAGES 2>/dev/null; then
	core_asset="$(sed -n '/^xray-mitm-[A-Za-z0-9._~+-]*\.apk$/p' PACKAGES)"
	luci_asset="$(sed -n '/^luci-app-xray-mitm-[A-Za-z0-9._~+-]*\.apk$/p' PACKAGES)"
	[ "$(printf '%s\n' "$core_asset" | wc -l | tr -d ' ')" = '1' ] || \
		die 'The release package list does not identify exactly one core APK.'
	[ "$(printf '%s\n' "$luci_asset" | wc -l | tr -d ' ')" = '1' ] || \
		die 'The release package list does not identify exactly one LuCI APK.'
else
	# v0.1.0 predates PACKAGES. Keep this fallback so the installer can install it.
	core_asset="$FALLBACK_CORE_ASSET"
	luci_asset="$FALLBACK_LUCI_ASSET"
fi

download "$base_url/SHA256SUMS" SHA256SUMS
download "$base_url/$core_asset" "$core_asset"
download "$base_url/$luci_asset" "$luci_asset"

awk -v core="$core_asset" -v luci="$luci_asset" \
	'$2 == core || $2 == luci { print }' SHA256SUMS > packages.sha256
[ "$(wc -l < packages.sha256 | tr -d ' ')" = '2' ] || \
	die 'The release checksum file does not contain both expected APKs.'

say 'Verifying SHA-256 checksums...'
sha256sum -c packages.sha256

if [ "${XRAY_MITM_SKIP_BACKUP:-0}" != '1' ] && \
	{ [ -e /etc/config/xray-mitm ] || [ -d /etc/xray-mitm ]; }
then
	backup_file="/root/xray-mitm-before-install-$(date +%Y%m%d-%H%M%S).tar.gz"
	set --
	[ ! -e /etc/config/xray-mitm ] || set -- "$@" /etc/config/xray-mitm
	[ ! -d /etc/xray-mitm ] || set -- "$@" /etc/xray-mitm
	tar -czf "$backup_file" "$@"
	chmod 0600 "$backup_file"
	say "Protected configuration backup: $backup_file"
fi

say 'Refreshing package metadata...'
apk update

say 'Installing xray-mitm and its LuCI page...'
apk add --allow-untrusted "./$core_asset" "./$luci_asset"

say ''
say 'Installation complete.'
say 'Open LuCI over HTTPS, then go to Services -> MITM Domain Fronting.'
say 'Install the packaged default configuration, create and activate a CA, then start the service.'
say 'Install only mycert.crt on client devices. Keep mycert.key on the router and in protected backups.'
say 'PassWall2 routing remains unchanged until you preview and apply it in LuCI.'
