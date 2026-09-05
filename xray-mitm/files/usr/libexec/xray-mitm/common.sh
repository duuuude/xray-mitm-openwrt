#!/bin/sh

# Shared constants and deliberately small helpers for xray-mitm.
# This file is sourced only by root-owned package scripts.

XRAY_MITM_ROOT="${XRAY_MITM_TEST_ROOT:-}"
if [ -n "$XRAY_MITM_ROOT" ]; then
	case "$XRAY_MITM_ROOT" in
		/tmp/*|/private/tmp/*) ;;
		*)
			printf '%s\n' "unsafe test root" >&2
			exit 1
			;;
	esac
fi

XRAY_MITM_UCI_PACKAGE="xray-mitm"
XRAY_MITM_UCI_SECTION="main"
XRAY_MITM_DIR="${XRAY_MITM_ROOT}/etc/xray-mitm"
XRAY_MITM_CONFIG="${XRAY_MITM_DIR}/config.json"
XRAY_MITM_CERT="${XRAY_MITM_DIR}/mycert.crt"
XRAY_MITM_KEY="${XRAY_MITM_DIR}/mycert.key"
XRAY_MITM_CA_DIR="${XRAY_MITM_DIR}/ca"
XRAY_MITM_SLOTS_DIR="${XRAY_MITM_CA_DIR}/slots"
XRAY_MITM_RECOVERY="${XRAY_MITM_CA_DIR}/recovery"
XRAY_MITM_SAMPLE="${XRAY_MITM_ROOT}/usr/share/xray-mitm/config.json.example"
XRAY_MITM_INIT="${XRAY_MITM_ROOT}/etc/init.d/xray-mitm"
XRAY_MITM_LIBEXEC="${XRAY_MITM_LIBEXEC:-${XRAY_MITM_ROOT}/usr/libexec/xray-mitm}"

xray_mitm_die() {
	printf '%s\n' "$*" >&2
	exit 1
}

xray_mitm_json_escape() {
	LC_ALL=C awk '
		BEGIN { first = 1 }
		{
			if (!first)
				printf "\\n"
			first = 0
			for (i = 1; i <= length($0); i++) {
				c = substr($0, i, 1)
				if (c == "\\")
					printf "\\\\"
				else if (c == "\"")
					printf "\\\""
				else if (c == "\t")
					printf "\\t"
				else if (c == "\r")
					printf "\\r"
				else if (c ~ /[[:cntrl:]]/)
					printf "?"
				else
					printf "%s", c
			}
		}'
}

xray_mitm_json_string() {
	printf '"'
	printf '%s' "$1" | xray_mitm_json_escape
	printf '"'
}

xray_mitm_uci_get() {
	uci -q get "${XRAY_MITM_UCI_PACKAGE}.${XRAY_MITM_UCI_SECTION}.$1" 2>/dev/null
}

xray_mitm_asset_dir() {
	local value
	value="$(xray_mitm_uci_get asset_dir)"
	[ -n "$value" ] || value="/usr/share/v2ray"
	printf '%s\n' "$value"
}

xray_mitm_socks_port() {
	# The packaged Xray configuration and optional PassWall2 node deliberately
	# share one fixed localhost-only interface. Keeping this non-configurable
	# prevents the health check and routing helper from silently diverging.
	printf '%s\n' 10808
}

xray_mitm_ensure_private_dir() {
	local path expected_uid stats
	path="$1"
	if [ -n "$XRAY_MITM_ROOT" ]; then expected_uid="$(id -u)"; else expected_uid=0; fi
	[ ! -L "$path" ] || return 1
	if [ -e "$path" ]; then
		[ -d "$path" ] || return 1
		stats="$(stat -c '%u %a' "$path" 2>/dev/null || true)"
		set -- $stats
		[ "$#" -eq 2 ] && [ "$1" = "$expected_uid" ] || return 1
	else
		mkdir "$path" || return 1
	fi
	[ -d "$path" ] && [ ! -L "$path" ] || return 1
	chmod 0700 "$path" || return 1
	stats="$(stat -c '%u %a' "$path" 2>/dev/null || true)"
	set -- $stats
	[ "$#" -eq 2 ] && [ "$1" = "$expected_uid" ] && [ "$2" = 700 ]
}

xray_mitm_ensure_private_dirs() {
	umask 077
	command -v stat >/dev/null 2>&1 || return 1
	xray_mitm_ensure_private_dir "$XRAY_MITM_DIR" || return 1
	xray_mitm_ensure_private_dir "$XRAY_MITM_CA_DIR" || return 1
	xray_mitm_ensure_private_dir "$XRAY_MITM_SLOTS_DIR"
}

xray_mitm_clock_sane() {
	local now
	now="$(date +%s 2>/dev/null)" || return 1
	case "$now" in ''|*[!0-9]*) return 1 ;; esac
	# Refuse certificate work while the router still has an epoch-like boot time.
	[ "$now" -ge 1577836800 ]
}

xray_mitm_cert_fingerprint() {
	local raw fingerprint
	[ -r "$1" ] || return 1
	raw="$(openssl x509 -in "$1" -noout -fingerprint -sha256 2>/dev/null)" || return 1
	fingerprint="$(printf '%s\n' "$raw" | sed -n 's/^.*=//; s/://g; y/ABCDEF/abcdef/; p')" || return 1
	xray_mitm_valid_fingerprint "$fingerprint" || return 1
	printf '%s\n' "$fingerprint"
}

xray_mitm_valid_fingerprint() {
	case "$1" in
		*[!0-9A-Fa-f]*|'') return 1 ;;
	esac
	[ "${#1}" -eq 64 ]
}

xray_mitm_refresh_provisioned() {
	local ready current
	ready=0
	if [ -s "$XRAY_MITM_CONFIG" ] && [ -s "$XRAY_MITM_CERT" ] && [ -s "$XRAY_MITM_KEY" ]; then
		ready=1
	fi
	current="$(xray_mitm_uci_get provisioned)"
	if [ "$current" != "$ready" ]; then
		uci -q set "${XRAY_MITM_UCI_PACKAGE}.${XRAY_MITM_UCI_SECTION}.provisioned=${ready}" || return 1
		uci -q commit "$XRAY_MITM_UCI_PACKAGE" || return 1
	fi
	return 0
}

xray_mitm_service_running() {
	"$XRAY_MITM_INIT" running >/dev/null 2>&1
}

xray_mitm_boot_enabled() {
	"$XRAY_MITM_INIT" enabled >/dev/null 2>&1
}
