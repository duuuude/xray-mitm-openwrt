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
if (ss -lntup 2>/dev/null || netstat -lntup 2>/dev/null) |
   grep -qE '127\.0\.0\.1:2005|::1:2005'; then
	printf 'present\n'
else
	printf 'absent\n'
fi
printf 'dns_example='
if timeout 8 nslookup example.com 127.0.0.1 2>/dev/null |
   grep -Eq '^Name:[[:space:]]*example\.com$'; then
	printf 'pass\n'
else
	printf 'fail\n'
fi
printf 'dns_openwrt='
if timeout 8 nslookup openwrt.org 127.0.0.1 2>/dev/null |
   grep -Eq '^Name:[[:space:]]*openwrt\.org$'; then
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
uci changes | wc -l | tr -d ' '
printf '\n'
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

listener_present() {
	(ss -lntup 2>/dev/null || netstat -lntup 2>/dev/null) |
		grep -qE '127\.0\.0\.1:2005|::1:2005'
}

rollback() {
	if [ "$installed" -eq 0 ]; then
		rollback_ok=1
		if [ -x "$init_target" ]; then
			"$init_target" disable >/dev/null 2>&1 || rollback_ok=0
			"$init_target" stop >/dev/null 2>&1 || rollback_ok=0
			if listener_present; then
				rollback_ok=0
			fi
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
test "$(uci changes | wc -l | tr -d ' ')" = 0
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
	if (ss -lntup 2>/dev/null || netstat -lntup 2>/dev/null) |
		grep -qE '127\.0\.0\.1:2005|::1:2005'; then
		break
	fi
	i=$((i + 1))
	sleep 1
done
test "$i" -lt 10

for name in example.com openwrt.org; do
	answer=$(timeout 8 nslookup "$name" 127.0.0.1 2>&1) || {
		printf '%s\n' "$answer" >&2
		exit 1
	}
	printf '%s\n' "$answer" | grep -Eq "^Name:[[:space:]]*$name$"
done

test "$(uci -q get passwall2.@global[0].enabled || true)" = 0
test "$(uci changes | wc -l | tr -d ' ')" = 0
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
test "$(uci changes | wc -l | tr -d ' ')" = 0
/etc/init.d/xray-mitm-dns stop
/etc/init.d/xray-mitm-dns disable
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
