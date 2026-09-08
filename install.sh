#!/bin/sh
set -eu

KEY_NAME='xray-mitm-feed-v1.pem'
PINNED_KEY_SHA256='3e0dc07ffef69d1512500b6add486381d8c261a8ec3fcce54fa403b35320df8a'
DEFAULT_KEY_URL='https://duuuude.github.io/xray-mitm-openwrt/feed/xray-mitm-feed-v1.pem'
DEFAULT_FEED_URL='https://duuuude.github.io/xray-mitm-openwrt/feed/25.12/all/packages.adb'

RELEASE_FILE="${XRAY_MITM_OPENWRT_RELEASE_FILE:-/etc/openwrt_release}"
PUBLIC_KEY_URL="${XRAY_MITM_PUBLIC_KEY_URL:-$DEFAULT_KEY_URL}"
PUBLIC_KEY_SHA256="${XRAY_MITM_PUBLIC_KEY_SHA256:-$PINNED_KEY_SHA256}"
FEED_URL="${XRAY_MITM_FEED_URL:-$DEFAULT_FEED_URL}"
APK_KEYS_DIR="${XRAY_MITM_APK_KEYS_DIR:-/etc/apk/keys}"
REPOSITORIES_DIR="${XRAY_MITM_REPOSITORIES_DIR:-/etc/apk/repositories.d}"
KEEP_DIR="${XRAY_MITM_KEEP_DIR:-/lib/upgrade/keep.d}"
APK_WORLD="${XRAY_MITM_APK_WORLD:-/etc/apk/world}"
BACKUP_DIR="${XRAY_MITM_BACKUP_DIR:-/root}"
CONFIG_FILE="${XRAY_MITM_CONFIG_FILE:-/etc/config/xray-mitm}"
STATE_DIR="${XRAY_MITM_STATE_DIR:-/etc/xray-mitm}"

KEY_FILE="$APK_KEYS_DIR/$KEY_NAME"
REPOSITORY_FILE="$REPOSITORIES_DIR/xray-mitm.list"
KEEP_FILE="$KEEP_DIR/xray-mitm-feed"

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
	status=$?
	trap - EXIT HUP INT TERM
	if [ "${feed_state_changed:-0}" = '1' ]; then
		if ! restore_feed_state; then
			printf 'ERROR: automatic feed rollback was incomplete. Use the protected backup.\n' >&2
		fi
	fi
	if [ -n "${work_dir:-}" ] && [ -d "$work_dir" ]; then
		rm -rf "$work_dir"
	fi
	exit "$status"
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

	[ "$major" -eq 25 ] && [ "$minor" -eq 12 ] && [ "$patch" -ge 5 ]
}

snapshot_file() {
	path="$1"
	name="$2"
	if [ -e "$path" ]; then
		cp -p "$path" "$work_dir/previous-$name"
		printf 'present\n' > "$work_dir/previous-$name.state"
	else
		printf 'absent\n' > "$work_dir/previous-$name.state"
	fi
}

restore_file() {
	path="$1"
	name="$2"
	state="$(cat "$work_dir/previous-$name.state")"
	if [ "$state" = 'present' ]; then
		mkdir -p "$(dirname "$path")"
		cp -p "$work_dir/previous-$name" "$path.rollback.$$"
		mv -f "$path.rollback.$$" "$path"
	else
		rm -f "$path"
	fi
}

restore_feed_state() {
	restore_status=0
	restore_file "$KEY_FILE" key || restore_status=1
	restore_file "$REPOSITORY_FILE" repository || restore_status=1
	restore_file "$KEEP_FILE" keep || restore_status=1
	restore_file "$APK_WORLD" world || restore_status=1
	return "$restore_status"
}

write_atomic() {
	source="$1"
	destination="$2"
	mode="$3"
	mkdir -p "$(dirname "$destination")"
	stage="$destination.new.$$"
	cp "$source" "$stage"
	chmod "$mode" "$stage"
	mv -f "$stage" "$destination"
}

[ "$(id -u)" = '0' ] || die 'Run this installer as root on the OpenWrt router.'
[ -r "$RELEASE_FILE" ] || die 'This does not appear to be an OpenWrt router.'

# shellcheck disable=SC1090
. "$RELEASE_FILE"
[ -n "${DISTRIB_RELEASE:-}" ] || die 'OpenWrt release information is incomplete.'
command -v apk >/dev/null 2>&1 || die 'This installer requires an APK-based OpenWrt release.'
command -v sha256sum >/dev/null 2>&1 || die 'sha256sum is required to verify the feed key.'
supported_openwrt_release || die "OpenWrt $DISTRIB_RELEASE is unsupported; use official OpenWrt 25.12.5 or a later 25.12 maintenance release."

case "$PUBLIC_KEY_SHA256" in
	*[!0-9a-f]*) die 'The pinned public-key SHA-256 value is invalid.' ;;
esac
[ "${#PUBLIC_KEY_SHA256}" -eq 64 ] || \
	die 'The pinned public-key SHA-256 value is invalid.'

umask 077
work_dir="$(mktemp -d "${TMPDIR:-/tmp}/xray-mitm-install.XXXXXX")"
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

say "OpenWrt: $DISTRIB_RELEASE"
say "Signed feed: $FEED_URL"
say 'Downloading the project feed public key...'
download "$PUBLIC_KEY_URL" "$work_dir/$KEY_NAME"

actual_key_sha256="$(sha256sum "$work_dir/$KEY_NAME" | awk '{print $1}')"
[ "$actual_key_sha256" = "$PUBLIC_KEY_SHA256" ] || \
	die "Feed public-key fingerprint mismatch (received $actual_key_sha256)."
grep -q '^-----BEGIN PUBLIC KEY-----$' "$work_dir/$KEY_NAME" || \
	die 'The downloaded feed key is not a PEM public key.'
if grep -q 'PRIVATE KEY' "$work_dir/$KEY_NAME"; then
	die 'The downloaded feed key unexpectedly contains private-key material.'
fi
say "Feed key verified: $actual_key_sha256"

mkdir -p "$BACKUP_DIR"
backup_file="$BACKUP_DIR/xray-mitm-before-install-$(date +%Y%m%d-%H%M%S).tar.gz"
set --
for path in \
	"$CONFIG_FILE" \
	"$STATE_DIR" \
	"$APK_WORLD" \
	"$KEY_FILE" \
	"$REPOSITORY_FILE" \
	"$KEEP_FILE"
do
	[ ! -e "$path" ] || set -- "$@" "$path"
done
if [ "$#" -gt 0 ]; then
	tar -czf "$backup_file" "$@"
	chmod 0600 "$backup_file"
	say "Protected backup: $backup_file"
fi

snapshot_file "$KEY_FILE" key
snapshot_file "$REPOSITORY_FILE" repository
snapshot_file "$KEEP_FILE" keep
snapshot_file "$APK_WORLD" world
feed_state_changed=1

write_atomic "$work_dir/$KEY_NAME" "$KEY_FILE" 0644
printf '%s\n' "$FEED_URL" > "$work_dir/xray-mitm.list"
write_atomic "$work_dir/xray-mitm.list" "$REPOSITORY_FILE" 0644
printf '%s\n%s\n' "$KEY_FILE" "$REPOSITORY_FILE" > "$work_dir/xray-mitm-feed.keep"
write_atomic "$work_dir/xray-mitm-feed.keep" "$KEEP_FILE" 0644

say 'Refreshing signed package metadata...'
if ! apk update; then
	if restore_feed_state; then
		feed_state_changed=0
		die 'APK rejected or could not download the package indexes; the previous feed state was restored.'
	fi
	die 'APK rejected the indexes and automatic rollback was incomplete; use the protected backup.'
fi

say 'Installing or updating xray-mitm and its LuCI page...'
if ! apk add xray-mitm luci-app-xray-mitm; then
	if restore_feed_state; then
		feed_state_changed=0
		die 'Package installation failed; the previous feed and package-selection state was restored.'
	fi
	die 'Package installation failed and automatic rollback was incomplete; use the protected backup.'
fi
feed_state_changed=0

if [ -r "$APK_WORLD" ]; then
	grep -Eq '^xray-mitm($|[<>=~])' "$APK_WORLD" || \
		die 'APK did not record xray-mitm as an explicitly managed package.'
	grep -Eq '^luci-app-xray-mitm($|[<>=~])' "$APK_WORLD" || \
		die 'APK did not record luci-app-xray-mitm as an explicitly managed package.'
fi

say ''
say 'Authenticated installation/update complete.'
say 'APK verified the signed feed and packages; --allow-untrusted was not used.'
say 'Open LuCI over HTTPS, then go to Services -> MITM Domain Fronting.'
say 'First installation: install the packaged default configuration, create and activate a CA, then start the service.'
say 'Existing installation: configuration, CA state, service state, and PassWall2 routing are preserved.'
say 'Install only mycert.crt on client devices. Keep mycert.key on the router and in protected backups.'
