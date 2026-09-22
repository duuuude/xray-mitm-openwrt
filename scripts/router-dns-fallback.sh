#!/bin/sh

# Install or inspect the narrowly scoped Xray-backed DNS fallback used when
# dnsmasq points at 127.0.0.1#2005 while PassWall2 is intentionally disabled.
# The helper owns only localhost:2005; it never edits UCI, PassWall2, firewall,
# certificates, WAN settings, or v2rayN.

set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
asset_dir="$script_dir/router-dns-fallback"
config_asset="$asset_dir/xray-config.json"
init_asset="$asset_dir/init.d-xray-mitm-dns"
router_host=${ROUTER_HOST:-192.168.1.1}
router_user=${ROUTER_USER:-root}
router_ssh_key=${ROUTER_SSH_KEY:-${HOME:-}/.ssh/xray-mitm-ax4200}
router_target="$router_user@$router_host"
marker_value=xray-mitm-dns-fallback-v1

die() {
	printf 'router-dns-fallback: %s\n' "$*" >&2
	exit 1
}

case "$router_host" in
	*[!A-Za-z0-9._:-]*) die 'ROUTER_HOST contains unsupported characters' ;;
esac
case "$router_user" in
	*[!A-Za-z0-9._-]*) die 'ROUTER_USER contains unsupported characters' ;;
esac

[ -r "$config_asset" ] || die "missing asset: $config_asset"
[ -r "$init_asset" ] || die "missing asset: $init_asset"
[ -r "$router_ssh_key" ] || die "SSH key is not readable: $router_ssh_key"

ssh_router() {
	ssh -o BatchMode=yes -o ConnectTimeout=10 -i "$router_ssh_key" "$router_target" "$@"
}

scp_router() {
	scp -O -q -i "$router_ssh_key" "$1" "$router_target:$2"
}

require_approval() {
	[ "${XRAY_MITM_DNS_FALLBACK_APPROVED:-}" = 1 ] ||
		die 'set XRAY_MITM_DNS_FALLBACK_APPROVED=1 for router mutation'
}

hash_file() {
	path=$1
	if command -v shasum >/dev/null 2>&1; then
		shasum -a 256 "$path" | awk '{print $1}'
	elif command -v sha256sum >/dev/null 2>&1; then
		sha256sum "$path" | awk '{print $1}'
	else
		die 'neither shasum nor sha256sum is available'
	fi
}

check() {
	ssh_router sh -s <<'REMOTE'
set -u
dns_lookup_ok() {
	name=$1
	attempt=1
	while [ "$attempt" -le 3 ]; do
		if timeout 4 nslookup "$name" 127.0.0.1 2>/dev/null |
			sed -n 's/^Name:[[:space:]]*//p' |
			sed 's/[[:space:]]*$//' |
			grep -Fqx "$name"; then
			return 0
		fi
		[ "$attempt" -ge 3 ] || sleep 1
		attempt=$((attempt + 1))
	done
	return 1
}

dns_result() {
	if dns_lookup_ok "$1"; then
		printf 'pass\n'
	else
		printf 'fail\n'
	fi
}

listener_state() {
	listener_output=
	if listener_output=$(ss -lntup 2>/dev/null); then
		if printf '%s\n' "$listener_output" |
			grep -qE '(^|[[:space:]])(127\.0\.0\.1:2005|\[::1\]:2005|::1:2005)([[:space:]]|$)'; then
			printf 'present\n'
		else
			printf 'absent\n'
		fi
		return 0
	fi
	if listener_output=$(netstat -lntup 2>/dev/null); then
		if printf '%s\n' "$listener_output" |
			grep -qE '(^|[[:space:]])(127\.0\.0\.1:2005|\[::1\]:2005|::1:2005)([[:space:]]|$)'; then
			printf 'present\n'
		else
			printf 'absent\n'
		fi
		return 0
	fi
	printf 'unknown\n'
	return 1
}

uci_changes_result() {
	if uci_changes_output=$(uci changes 2>/dev/null); then
		if [ -n "$uci_changes_output" ]; then
			printf 'pending\n'
		else
			printf '0\n'
		fi
	else
		printf 'unknown\n'
	fi
}

printf 'passwall2='
uci -q get passwall2.@global[0].enabled || true
printf 'dns_noresolv='
uci -q get dhcp.@dnsmasq[0].noresolv || true
printf 'dns_server='
uci -q get dhcp.@dnsmasq[0].server || true
printf 'dns_fallback_marker='
if [ -f /etc/xray-mitm/dns-fallback.managed ] &&
   [ "$(cat /etc/xray-mitm/dns-fallback.managed 2>/dev/null)" = xray-mitm-dns-fallback-v1 ]; then
	printf 'present\n'
else
	printf 'absent\n'
fi
printf 'listener='
listener_state_value=$(listener_state) || listener_state_value=unknown
printf '%s\n' "$listener_state_value"
printf 'dns_example='
dns_result example.com
printf 'dns_openwrt='
dns_result openwrt.org
printf 'dns_iana='
dns_result iana.org
printf 'dns_checks='
if dns_lookup_ok openwrt.org && dns_lookup_ok iana.org; then
	printf 'pass\n'
else
	printf 'fail\n'
fi
printf 'wan='
if ping -c 1 -W 3 1.1.1.1 >/dev/null 2>&1; then
	printf 'pass\n'
else
	printf 'fail\n'
fi
printf 'uci_changes='
uci_changes_result
REMOTE
}

install_fallback() {
	config_hash=$(hash_file "$config_asset")
	init_hash=$(hash_file "$init_asset")
	stage=$(ssh_router 'mktemp -d /tmp/xray-mitm-dns-fallback.XXXXXX')
	cleanup_stage() {
		ssh_router rm -rf "$stage" >/dev/null 2>&1 || true
	}
	trap cleanup_stage EXIT INT TERM
	scp_router "$config_asset" "$stage/config.json"
	scp_router "$init_asset" "$stage/init"
	ssh_router sh -s -- "$stage" "$config_hash" "$init_hash" "$marker_value" <<'REMOTE'
set -eu
stage=$1
expected_config_hash=$2
expected_init_hash=$3
marker_value=$4
config_target=/etc/xray-mitm/dns-proxy.json
init_target=/etc/init.d/xray-mitm-dns
marker_target=/etc/xray-mitm/dns-fallback.managed
installed=0

dns_lookup_ok() {
	name=$1
	attempt=1
	while [ "$attempt" -le 3 ]; do
		if timeout 4 nslookup "$name" 127.0.0.1 2>&1 |
			sed -n 's/^Name:[[:space:]]*//p' |
			sed 's/[[:space:]]*$//' |
			grep -Fqx "$name"; then
			return 0
		fi
		[ "$attempt" -ge 3 ] || sleep 1
		attempt=$((attempt + 1))
	done
	return 1
}

listener_state() {
	listener_output=
	if listener_output=$(ss -lntup 2>/dev/null); then
		if printf '%s\n' "$listener_output" |
			grep -qE '(^|[[:space:]])(127\.0\.0\.1:2005|\[::1\]:2005|::1:2005)([[:space:]]|$)'; then
			printf 'present\n'
		else
			printf 'absent\n'
		fi
		return 0
	fi
	if listener_output=$(netstat -lntup 2>/dev/null); then
		if printf '%s\n' "$listener_output" |
			grep -qE '(^|[[:space:]])(127\.0\.0\.1:2005|\[::1\]:2005|::1:2005)([[:space:]]|$)'; then
			printf 'present\n'
		else
			printf 'absent\n'
		fi
		return 0
	fi
	printf 'unknown\n'
	return 1
}

uci_changes_clean() {
	if ! uci_changes_output=$(uci changes 2>/dev/null); then
		printf '%s\n' 'router_dns_fallback: unable to inspect UCI changes' >&2
		return 1
	fi
	if [ -n "$uci_changes_output" ]; then
		printf '%s\n' 'router_dns_fallback: refusing while UCI changes are pending' >&2
		return 1
	fi
}

rollback() {
	if [ "$installed" -eq 0 ]; then
		rollback_ok=1
		if [ -x "$init_target" ]; then
			if "$init_target" disable >/dev/null 2>&1; then :; else rollback_ok=0; fi
			if "$init_target" stop >/dev/null 2>&1; then :; else rollback_ok=0; fi
		fi
		if listener_state_value=$(listener_state); then
			if [ "$listener_state_value" != absent ]; then
				rollback_ok=0
			fi
		else
			rollback_ok=0
		fi
		if [ "$rollback_ok" -eq 1 ]; then
			rm -f "$config_target" "$init_target" "$marker_target"
		else
			printf '%s\n' 'router_dns_fallback: rollback incomplete; preserving helper files' >&2
		fi
	fi
	rm -rf "$stage"
}
trap rollback EXIT INT TERM

test "$(sha256sum "$stage/config.json" | awk '{print $1}')" = "$expected_config_hash"
test "$(sha256sum "$stage/init" | awk '{print $1}')" = "$expected_init_hash"
test ! -e "$config_target"
test ! -e "$init_target"
test ! -e "$marker_target"
test "$(uci -q get passwall2.@global[0].enabled || true)" = 0
test "$(uci -q get dhcp.@dnsmasq[0].server || true)" = '127.0.0.1#2005'
uci_changes_clean
test -x /usr/bin/xray
XRAY_LOCATION_ASSET=/usr/share/v2ray /usr/bin/xray run -test -c "$stage/config.json" >/dev/null 2>&1

chmod 0600 "$stage/config.json"
chmod 0755 "$stage/init"
cp -p "$stage/config.json" "$config_target"
cp -p "$stage/init" "$init_target"
chmod 0600 "$config_target"
chmod 0755 "$init_target"
printf '%s\n' "$marker_value" > "$marker_target"
chmod 0600 "$marker_target"

"$init_target" enable
"$init_target" start
i=0
while [ "$i" -lt 10 ]; do
	if listener_state_value=$(listener_state); then
		if [ "$listener_state_value" = present ]; then
			break
		fi
	else
		printf '%s\n' 'router_dns_fallback: unable to inspect DNS listener' >&2
		exit 1
	fi
	i=$((i + 1))
	sleep 1
done
test "$i" -lt 10

for name in openwrt.org iana.org; do
	dns_lookup_ok "$name" || {
		printf 'router_dns_fallback: stable DNS probe failed for %s\n' "$name" >&2
		exit 1
	}
done

test "$(uci -q get passwall2.@global[0].enabled || true)" = 0
uci_changes_clean
ping -c 1 -W 3 1.1.1.1 >/dev/null 2>&1
installed=1
trap - EXIT INT TERM
rm -rf "$stage"
printf 'router_dns_fallback=installed\n'
REMOTE
	trap - EXIT INT TERM
}

remove_fallback() {
	ssh_router sh -s <<'REMOTE'
set -eu

listener_state() {
	listener_output=
	if listener_output=$(ss -lntup 2>/dev/null); then
		if printf '%s\n' "$listener_output" |
			grep -qE '(^|[[:space:]])(127\.0\.0\.1:2005|\[::1\]:2005|::1:2005)([[:space:]]|$)'; then
			printf 'present\n'
		else
			printf 'absent\n'
		fi
		return 0
	fi
	if listener_output=$(netstat -lntup 2>/dev/null); then
		if printf '%s\n' "$listener_output" |
			grep -qE '(^|[[:space:]])(127\.0\.0\.1:2005|\[::1\]:2005|::1:2005)([[:space:]]|$)'; then
			printf 'present\n'
		else
			printf 'absent\n'
		fi
		return 0
	fi
	printf 'unknown\n'
	return 1
}

uci_changes_clean() {
	if ! uci_changes_output=$(uci changes 2>/dev/null); then
		printf '%s\n' 'router_dns_fallback: unable to inspect UCI changes' >&2
		return 1
	fi
	if [ -n "$uci_changes_output" ]; then
		printf '%s\n' 'router_dns_fallback: refusing while UCI changes are pending' >&2
		return 1
	fi
}

test -f /etc/xray-mitm/dns-fallback.managed
test "$(cat /etc/xray-mitm/dns-fallback.managed)" = xray-mitm-dns-fallback-v1
dnsmasq_config=$(uci -q show dhcp.@dnsmasq[0]) || {
	printf '%s\n' 'refusing removal because dnsmasq configuration could not be read' >&2
	exit 1
}
if printf '%s\n' "$dnsmasq_config" |
	grep -Eq '\.server=.*127\.0\.0\.1#2005'; then
	printf '%s\n' 'refusing removal while dnsmasq still targets 127.0.0.1#2005' >&2
	exit 1
fi
uci_changes_clean
removal_ok=1
if /etc/init.d/xray-mitm-dns stop; then :; else removal_ok=0; fi
if /etc/init.d/xray-mitm-dns disable; then :; else removal_ok=0; fi
i=0
while [ "$i" -lt 10 ]; do
	if listener_state_value=$(listener_state); then
		if [ "$listener_state_value" = absent ]; then
			break
		fi
	else
		removal_ok=0
		break
	fi
	i=$((i + 1))
	sleep 1
done
if [ "$removal_ok" -ne 1 ] || [ "$i" -ge 10 ]; then
	printf '%s\n' 'router_dns_fallback: refusing removal until DNS listener absence is verified' >&2
	exit 1
fi
rm -f /etc/xray-mitm/dns-proxy.json /etc/init.d/xray-mitm-dns /etc/xray-mitm/dns-fallback.managed
printf 'router_dns_fallback=removed\n'
REMOTE
}

case "${1:-}" in
	check) check ;;
	install)
		require_approval
		install_fallback
		;;
	remove)
		require_approval
		remove_fallback
		;;
	*)
		printf '%s\n' \
			'Usage: scripts/router-dns-fallback.sh check|install|remove' \
			'  install/remove require XRAY_MITM_DNS_FALLBACK_APPROVED=1.' >&2
		exit 64
		;;
esac
