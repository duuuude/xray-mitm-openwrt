#!/bin/sh
set -eu

KEY_NAME='xray-mitm-feed-v1.pem'
OPKG_KEY_DOWNLOAD_NAME='xray-mitm-feed-v1.usign.pub'
OPKG_FEED_NAME='xray_mitm'
PINNED_KEY_SHA256='3e0dc07ffef69d1512500b6add486381d8c261a8ec3fcce54fa403b35320df8a'
DEFAULT_KEY_URL='https://duuuude.github.io/xray-mitm-openwrt/feed/xray-mitm-feed-v1.pem'
DEFAULT_FEED_URL='https://duuuude.github.io/xray-mitm-openwrt/feed/25.12/all/packages.adb'

RELEASE_FILE="${XRAY_MITM_OPENWRT_RELEASE_FILE:-/etc/openwrt_release}"
PUBLIC_KEY_URL="${XRAY_MITM_PUBLIC_KEY_URL:-$DEFAULT_KEY_URL}"
PUBLIC_KEY_SHA256="${XRAY_MITM_PUBLIC_KEY_SHA256:-$PINNED_KEY_SHA256}"
FEED_URL="${XRAY_MITM_FEED_URL:-$DEFAULT_FEED_URL}"
OPKG_PUBLIC_KEY_URL="${XRAY_MITM_OPKG_PUBLIC_KEY_URL:-}"
OPKG_PUBLIC_KEY_SHA256="${XRAY_MITM_OPKG_PUBLIC_KEY_SHA256:-}"
OPKG_FEED_URL="${XRAY_MITM_OPKG_FEED_URL:-}"
APK_KEYS_DIR="${XRAY_MITM_APK_KEYS_DIR:-/etc/apk/keys}"
REPOSITORIES_DIR="${XRAY_MITM_REPOSITORIES_DIR:-/etc/apk/repositories.d}"
OPKG_KEYS_DIR="${XRAY_MITM_OPKG_KEYS_DIR:-/etc/opkg/keys}"
OPKG_FEEDS_FILE="${XRAY_MITM_OPKG_FEEDS_FILE:-/etc/opkg/customfeeds.conf}"
OPKG_CONF_FILE="${XRAY_MITM_OPKG_CONF_FILE:-/etc/opkg.conf}"
KEEP_DIR="${XRAY_MITM_KEEP_DIR:-/lib/upgrade/keep.d}"
APK_WORLD="${XRAY_MITM_APK_WORLD:-/etc/apk/world}"
BACKUP_DIR="${XRAY_MITM_BACKUP_DIR:-/root}"
CONFIG_FILE="${XRAY_MITM_CONFIG_FILE:-/etc/config/xray-mitm}"
STATE_DIR="${XRAY_MITM_STATE_DIR:-/etc/xray-mitm}"
BACKUP_PREFIX='xray-mitm-before-install-'
BACKUP_RETENTION=3

PLATFORM_RELEASE=''
PLATFORM_PACKAGE_MANAGER=''
APK_BIN=''
OPKG_BIN=''
ACTIVE_KEY_NAME=''
ACTIVE_PUBLIC_KEY_URL=''
ACTIVE_PUBLIC_KEY_SHA256=''
ACTIVE_FEED_URL=''
OPKG_KEY_FINGERPRINT=''

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

validate_https_url() {
	url="$1"
	label="$2"

	case "$url" in
		https://*) ;;
		*) die "The $label must use HTTPS." ;;
	esac
	case "$url" in
		*[![:print:]]*|*[[:space:]]*)
			die "The $label contains whitespace or control characters."
			;;
	esac
	authority_and_path="${url#https://}"
	authority="${authority_and_path%%[/?#]*}"
	case "$authority" in
		''|*@*) die "The $label must contain a host and no credentials." ;;
	esac
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

supported_apk_release() {
	release="$1"
	version="${release%%-*}"
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

	[ "$major" -eq 25 ] && [ "$minor" -eq 12 ]
}

supported_opkg_release() {
	release="$1"
	version="${release%%-*}"
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

	[ "$major" -eq 24 ] && [ "$minor" -eq 10 ]
}

detect_platform() {
	[ -r "$RELEASE_FILE" ] || die 'This does not appear to be an OpenWrt router.'

	# shellcheck disable=SC1090
	. "$RELEASE_FILE"
	[ -n "${DISTRIB_RELEASE:-}" ] || die 'OpenWrt release information is incomplete.'

	PLATFORM_RELEASE="$DISTRIB_RELEASE"
	APK_BIN="$(command -v apk 2>/dev/null || true)"
	OPKG_BIN="$(command -v opkg 2>/dev/null || true)"
	if supported_apk_release "$PLATFORM_RELEASE" && [ -n "$APK_BIN" ]; then
		PLATFORM_PACKAGE_MANAGER='apk'
	elif supported_opkg_release "$PLATFORM_RELEASE" && [ -n "$OPKG_BIN" ]; then
		PLATFORM_PACKAGE_MANAGER='opkg'
	else
		PLATFORM_PACKAGE_MANAGER='unknown'
	fi
}

check_platform_support() {
	case "$PLATFORM_PACKAGE_MANAGER" in
		apk)
			supported_apk_release "$PLATFORM_RELEASE" || \
				die "OpenWrt $PLATFORM_RELEASE is unsupported; use official OpenWrt 25.12.x with APK or 24.10.x with OPKG."
			command -v sha256sum >/dev/null 2>&1 || die 'sha256sum is required to verify the feed key.'
			;;
	opkg)
			supported_opkg_release "$PLATFORM_RELEASE" || \
				die "OpenWrt $PLATFORM_RELEASE is unsupported; use official OpenWrt 24.10.x with OPKG."
			command -v sha256sum >/dev/null 2>&1 || die 'sha256sum is required to verify the feed key.'
			command -v usign >/dev/null 2>&1 || die 'usign is required to derive the OPKG trust-key fingerprint.'
			[ -r "$OPKG_CONF_FILE" ] || \
				die "OPKG signature checking is not configured; required file is $OPKG_CONF_FILE."
			grep -Eq '^[[:space:]]*option[[:space:]]+check_signature([[:space:]]+1)?[[:space:]]*$' "$OPKG_CONF_FILE" || \
				die 'OPKG signature checking is not enabled; refusing an unauthenticated package path.'
			[ -n "$OPKG_PUBLIC_KEY_URL" ] || \
				die 'OpenWrt 24.10 OPKG installation requires XRAY_MITM_OPKG_PUBLIC_KEY_URL; no public 24.10 feed is configured yet.'
			[ -n "$OPKG_PUBLIC_KEY_SHA256" ] || \
				die 'OpenWrt 24.10 OPKG installation requires XRAY_MITM_OPKG_PUBLIC_KEY_SHA256; no public 24.10 feed is configured yet.'
			[ -n "$OPKG_FEED_URL" ] || \
				die 'OpenWrt 24.10 OPKG installation requires XRAY_MITM_OPKG_FEED_URL; no public 24.10 feed is configured yet.'
			;;
		*)
			die "OpenWrt $PLATFORM_RELEASE has no matching supported package manager; use 25.12.x with APK or 24.10.x with OPKG."
			;;
	esac
}

select_backend_paths() {
	case "$PLATFORM_PACKAGE_MANAGER" in
		apk)
			ACTIVE_KEY_NAME="$KEY_NAME"
			ACTIVE_PUBLIC_KEY_URL="$PUBLIC_KEY_URL"
			ACTIVE_PUBLIC_KEY_SHA256="$PUBLIC_KEY_SHA256"
			ACTIVE_FEED_URL="$FEED_URL"
			KEY_FILE="$APK_KEYS_DIR/$KEY_NAME"
			REPOSITORY_FILE="$REPOSITORIES_DIR/xray-mitm.list"
			;;
	opkg)
			ACTIVE_KEY_NAME="$OPKG_KEY_DOWNLOAD_NAME"
			ACTIVE_PUBLIC_KEY_URL="$OPKG_PUBLIC_KEY_URL"
			ACTIVE_PUBLIC_KEY_SHA256="$OPKG_PUBLIC_KEY_SHA256"
			ACTIVE_FEED_URL="$OPKG_FEED_URL"
			KEY_FILE=''
			REPOSITORY_FILE="$OPKG_FEEDS_FILE"
			;;
		*) die 'No supported package backend was selected.' ;;
	esac
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
	if [ "$PLATFORM_PACKAGE_MANAGER" = 'apk' ]; then
		restore_file "$APK_WORLD" world || restore_status=1
	fi
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

prune_backups() {
	backup_list="$work_dir/backups"
	backup_sorted="$work_dir/backups.sorted"
	: > "$backup_list"
	for candidate in "${BACKUP_DIR}/${BACKUP_PREFIX}"*.tar.gz; do
		[ -f "$candidate" ] || continue
		printf '%s\n' "$candidate" >> "$backup_list"
	done
	LC_ALL=C sort -r "$backup_list" > "$backup_sorted"

	backup_count=0
	while IFS= read -r candidate; do
		[ -n "$candidate" ] || continue
		backup_count=$((backup_count + 1))
		if [ "$backup_count" -le "$BACKUP_RETENTION" ]; then
			chmod 0600 "$candidate"
		else
			rm -f "$candidate"
		fi
	done < "$backup_sorted"
}

[ "$(id -u)" = '0' ] || die 'Run this installer as root on the OpenWrt router.'
detect_platform
check_platform_support
select_backend_paths

case "$ACTIVE_PUBLIC_KEY_SHA256" in
	*[!0-9a-f]*) die 'The pinned public-key SHA-256 value is invalid.' ;;
esac
[ "${#ACTIVE_PUBLIC_KEY_SHA256}" -eq 64 ] || \
	die 'The pinned public-key SHA-256 value is invalid.'

umask 077
work_dir="$(mktemp -d "${TMPDIR:-/tmp}/xray-mitm-install.XXXXXX")"
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

say "OpenWrt: $PLATFORM_RELEASE"
say "Package manager: $PLATFORM_PACKAGE_MANAGER"
validate_https_url "$ACTIVE_PUBLIC_KEY_URL" 'feed public-key URL'
validate_https_url "$ACTIVE_FEED_URL" 'signed feed URL'
say 'Downloading the project feed public key...'
downloaded_key_file="$work_dir/$ACTIVE_KEY_NAME"
download "$ACTIVE_PUBLIC_KEY_URL" "$downloaded_key_file"

actual_key_sha256="$(sha256sum "$downloaded_key_file" | awk '{print $1}')"
[ "$actual_key_sha256" = "$ACTIVE_PUBLIC_KEY_SHA256" ] || \
	die "Feed public-key SHA-256 mismatch (received $actual_key_sha256)."
if [ "$PLATFORM_PACKAGE_MANAGER" = 'apk' ]; then
	grep -q '^-----BEGIN PUBLIC KEY-----$' "$downloaded_key_file" || \
		die 'The downloaded feed key is not a PEM public key.'
else
	grep -q '^untrusted comment:' "$downloaded_key_file" || \
		die 'The downloaded OPKG feed key is not a usign public key.'
	OPKG_KEY_FINGERPRINT="$(usign -F -p "$downloaded_key_file" 2>/dev/null || true)"
	case "$OPKG_KEY_FINGERPRINT" in
		''|*[!0-9A-Fa-f]*) die 'The downloaded OPKG feed key has an invalid usign fingerprint.' ;;
	esac
	[ "${#OPKG_KEY_FINGERPRINT}" -eq 64 ] || \
		die 'The downloaded OPKG feed key has an invalid usign fingerprint.'
	ACTIVE_KEY_NAME="$OPKG_KEY_FINGERPRINT"
	KEY_FILE="$OPKG_KEYS_DIR/$OPKG_KEY_FINGERPRINT"
fi
if grep -q 'PRIVATE KEY' "$downloaded_key_file"; then
	die 'The downloaded feed key unexpectedly contains private-key material.'
fi
say "Feed key verified: $actual_key_sha256"

mkdir -p "$BACKUP_DIR"
backup_file="$BACKUP_DIR/${BACKUP_PREFIX}$(date +%Y%m%d-%H%M%S).tar.gz"
set --
for path in \
	"$CONFIG_FILE" \
	"$STATE_DIR" \
	"$KEY_FILE" \
	"$REPOSITORY_FILE" \
	"$KEEP_FILE"
do
	[ ! -e "$path" ] || set -- "$@" "$path"
done
if [ "$PLATFORM_PACKAGE_MANAGER" = 'apk' ] && [ -e "$APK_WORLD" ]; then
	set -- "$@" "$APK_WORLD"
fi
if [ "$#" -gt 0 ]; then
	tar -czf "$backup_file" "$@"
	chmod 0600 "$backup_file"
	say "Protected backup: $backup_file"
fi
prune_backups

snapshot_file "$KEY_FILE" key
snapshot_file "$REPOSITORY_FILE" repository
snapshot_file "$KEEP_FILE" keep
if [ "$PLATFORM_PACKAGE_MANAGER" = 'apk' ]; then
	snapshot_file "$APK_WORLD" world
fi
feed_state_changed=1

write_atomic "$downloaded_key_file" "$KEY_FILE" 0644
if [ "$PLATFORM_PACKAGE_MANAGER" = 'apk' ]; then
	printf '%s\n' "$ACTIVE_FEED_URL" > "$work_dir/xray-mitm.list"
	write_atomic "$work_dir/xray-mitm.list" "$REPOSITORY_FILE" 0644
else
	if [ -f "$REPOSITORY_FILE" ]; then
		awk -v feed_name="$OPKG_FEED_NAME" -v feed_url="$ACTIVE_FEED_URL" '
			$1 == "src/gz" && $2 == feed_name {
				if (!replaced) print "src/gz " feed_name " " feed_url
				replaced = 1
				next
			}
			{ print }
			END {
				if (!replaced) print "src/gz " feed_name " " feed_url
			}
		' "$REPOSITORY_FILE" > "$work_dir/xray-mitm-opkg.conf"
	else
		printf 'src/gz %s %s\n' "$OPKG_FEED_NAME" "$ACTIVE_FEED_URL" > "$work_dir/xray-mitm-opkg.conf"
	fi
	write_atomic "$work_dir/xray-mitm-opkg.conf" "$REPOSITORY_FILE" 0644
fi
printf '%s\n%s\n' "$KEY_FILE" "$REPOSITORY_FILE" > "$work_dir/xray-mitm-feed.keep"
write_atomic "$work_dir/xray-mitm-feed.keep" "$KEEP_FILE" 0644

say 'Refreshing signed package metadata...'
if [ "$PLATFORM_PACKAGE_MANAGER" = 'apk' ]; then
	if ! "$APK_BIN" update; then
		if restore_feed_state; then
			feed_state_changed=0
			die 'APK rejected or could not download the package indexes; the previous feed state was restored.'
		fi
		die 'APK rejected the indexes and automatic rollback was incomplete; use the protected backup.'
	fi

	say 'Installing or updating xray-mitm and its LuCI page...'
	if ! "$APK_BIN" add xray-mitm luci-app-xray-mitm; then
		if restore_feed_state; then
			feed_state_changed=0
			die 'Package installation failed; the previous feed and package-selection state was restored.'
		fi
		die 'Package installation failed and automatic rollback was incomplete; use the protected backup.'
	fi

	# OpenWrt apk v3's add operation records missing packages in world, but it does
	# not upgrade an already installed package merely because a newer candidate is
	# available. Run a targeted upgrade so repeat invocations update these two
	# packages without performing an unsafe system-wide upgrade.
	if ! "$APK_BIN" upgrade xray-mitm luci-app-xray-mitm; then
		if restore_feed_state; then
			feed_state_changed=0
			die 'Package upgrade failed; the previous feed and package-selection state was restored.'
		fi
		die 'Package upgrade failed and automatic rollback was incomplete; use the protected backup.'
	fi
else
	say 'Installing or updating xray-mitm and its LuCI page...'
	if ! "$OPKG_BIN" update; then
		if restore_feed_state; then
			feed_state_changed=0
			die 'OPKG rejected or could not download the signed package indexes; the previous feed state was restored.'
		fi
		die 'OPKG rejected the indexes and automatic rollback was incomplete; use the protected backup.'
	fi

	if ! "$OPKG_BIN" install xray-mitm luci-app-xray-mitm; then
		if restore_feed_state; then
			feed_state_changed=0
			die 'OPKG package installation failed; the previous feed state was restored.'
		fi
		die 'OPKG package installation failed and automatic rollback was incomplete; use the protected backup.'
	fi

	if ! "$OPKG_BIN" upgrade xray-mitm luci-app-xray-mitm; then
		if restore_feed_state; then
			feed_state_changed=0
			die 'OPKG package upgrade failed; the previous feed state was restored.'
		fi
		die 'OPKG package upgrade failed and automatic rollback was incomplete; use the protected backup.'
	fi
fi
feed_state_changed=0

if [ "$PLATFORM_PACKAGE_MANAGER" = 'apk' ] && [ -r "$APK_WORLD" ]; then
	grep -Eq '^xray-mitm($|[<>=~])' "$APK_WORLD" || \
		die 'APK did not record xray-mitm as an explicitly managed package.'
	grep -Eq '^luci-app-xray-mitm($|[<>=~])' "$APK_WORLD" || \
		die 'APK did not record luci-app-xray-mitm as an explicitly managed package.'
fi

say ''
say 'Authenticated installation/update complete.'
if [ "$PLATFORM_PACKAGE_MANAGER" = 'apk' ]; then
	say 'APK verified the signed feed and packages; --allow-untrusted was not used.'
else
	say 'OPKG verified the signed package index; no unsigned or forced dependency install was used.'
fi
say 'Open LuCI over HTTPS, then go to Services -> MITM Domain Fronting.'
say 'In Basic -> Setup, select Set up automatically when setup is needed.'
say 'Download the public certificate there, then use Basic -> Routing for optional PassWall2 rules.'
say 'Existing configuration, CA state, service state, and PassWall2 routing are preserved.'
say 'Install only mycert.crt on client devices. Keep mycert.key on the router and in protected backups.'
