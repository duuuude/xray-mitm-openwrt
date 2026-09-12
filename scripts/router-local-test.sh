#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)
user_home=${HOME:-}

router_host=${ROUTER_HOST:-192.168.1.1}
router_user=${ROUTER_USER:-root}
if [ -n "${ROUTER_SSH_KEY:-}" ]; then
  router_ssh_key=$ROUTER_SSH_KEY
else
  [ -n "$user_home" ] || {
    printf '%s\n' 'ROUTER_SSH_KEY is required when HOME is not set.' >&2
    exit 1
  }
  router_ssh_key=$user_home/.ssh/xray-mitm-ax4200
fi
router_backup_dir=${ROUTER_BACKUP_DIR:-/root/xray-mitm-local-backup}
remote_stage_dir=/tmp/xray-mitm-local-stage
router_target=$router_user@$router_host

candidate_names='passwall2 xray-mitmctl xray-mitm.uc overview.js state.js'

die() {
  printf 'router-local-test: %s\n' "$*"
  exit 1
}

usage() {
  cat <<'EOF'
Usage:
  sh scripts/router-local-test.sh validate
  sh scripts/router-local-test.sh config-validate
  sh scripts/router-local-test.sh stage
  sh scripts/router-local-test.sh check
  sh scripts/router-local-test.sh restore

Commands:
  validate  Run the complete offline validator and detect the bundled Node.js.
  config-validate
            Validate the packaged Xray sample with the router's configured
            asset directory; only a temporary file is copied to the router.
  stage     Protect the router originals and stage the exact local candidate.
  check     Read router/service/setup state and file hashes without changing it.
  restore   Restore the protected originals without restarting services or routing.

The stage command does not build an APK, restart Xray, or apply PassWall2 rules.
It only copies the five candidate files needed for the real LuCI browser gate.
Keep the browser test and any routing apply as deliberate, separate actions.

Environment overrides:
  ROUTER_HOST       Default: 192.168.1.1
  ROUTER_USER       Default: root
  ROUTER_SSH_KEY    Default: ~/.ssh/xray-mitm-ax4200
  ROUTER_BACKUP_DIR Default: /root/xray-mitm-local-backup
  NODE_BIN          Optional Node.js executable for validate
  ROUTER_SKIP_VALIDATE=1  Skip validation in stage only after validating unchanged code
  ROUTER_ALLOW_DIRTY=1    Allow stage from an uncommitted worktree (avoid for release evidence)
EOF
}

validate_backup_dir() {
  case "$router_backup_dir" in
    /*) ;;
    *) die "ROUTER_BACKUP_DIR must be an absolute path" ;;
  esac
  case "$router_backup_dir" in
    *[!A-Za-z0-9_./-]*) die "ROUTER_BACKUP_DIR contains an unsafe character" ;;
  esac
}

require_router_tools() {
  [ -r "$router_ssh_key" ] || die "SSH key is not readable: $router_ssh_key"
  command -v ssh >/dev/null 2>&1 || die 'ssh is required on the Mac'
  command -v scp >/dev/null 2>&1 || die 'scp is required on the Mac'
}

ssh_router() {
  ssh \
    -o BatchMode=yes \
    -o ConnectTimeout=8 \
    -o ServerAliveInterval=5 \
    -o ServerAliveCountMax=2 \
    -o StrictHostKeyChecking=accept-new \
    -i "$router_ssh_key" \
    "$router_target" "$@"
}

scp_to_router() {
  scp \
    -O \
    -q \
    -o BatchMode=yes \
    -o ConnectTimeout=8 \
    -o StrictHostKeyChecking=accept-new \
    -i "$router_ssh_key" \
    "$1" "$router_target:$2"
}

candidate_source() {
  case "$1" in
    passwall2) printf '%s\n' "$project_dir/xray-mitm/files/usr/libexec/xray-mitm/passwall2" ;;
    xray-mitmctl) printf '%s\n' "$project_dir/xray-mitm/files/usr/sbin/xray-mitmctl" ;;
    xray-mitm.uc) printf '%s\n' "$project_dir/luci-app-xray-mitm/root/usr/share/rpcd/ucode/xray-mitm.uc" ;;
    overview.js) printf '%s\n' "$project_dir/luci-app-xray-mitm/htdocs/luci-static/resources/view/xray-mitm/overview.js" ;;
    state.js) printf '%s\n' "$project_dir/luci-app-xray-mitm/htdocs/luci-static/resources/xray-mitm/state.js" ;;
    *) die "unknown candidate file: $1" ;;
  esac
}

config_sample_source() {

  printf '%s\n' "$project_dir/xray-mitm/files/usr/share/xray-mitm/config.json.example"
}

live_path() {
  case "$1" in
    passwall2) printf '%s\n' /usr/libexec/xray-mitm/passwall2 ;;
    xray-mitmctl) printf '%s\n' /usr/sbin/xray-mitmctl ;;
    xray-mitm.uc) printf '%s\n' /usr/share/rpcd/ucode/xray-mitm.uc ;;
    overview.js) printf '%s\n' /www/luci-static/resources/view/xray-mitm/overview.js ;;
    state.js) printf '%s\n' /www/luci-static/resources/xray-mitm/state.js ;;
    *) die "unknown live file: $1" ;;
  esac
}

hash_file() {
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk 'NR == 1 { print $1 }'
  elif command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk 'NR == 1 { print $1 }'
  else
    die 'shasum or sha256sum is required on the Mac'
  fi
}

remote_hash() {
  remote_hash_value=$(ssh_router sha256sum "$1" | awk 'NR == 1 { print $1 }')
  [ -n "$remote_hash_value" ] || die "router returned no hash for $1"
  printf '%s\n' "$remote_hash_value"
}

check_worktree() {
  if [ "${ROUTER_ALLOW_DIRTY:-0}" != 1 ] && [ -n "$(git -C "$project_dir" status --porcelain)" ]; then
    die 'worktree is dirty; commit or set ROUTER_ALLOW_DIRTY=1 for a deliberate local test'
  fi
}

detect_node() {
  if [ -n "${NODE_BIN:-}" ]; then
    [ -x "$NODE_BIN" ] || die "NODE_BIN is not executable: $NODE_BIN"
    printf '%s\n' "$NODE_BIN"
    return 0
  fi

  if node_path=$(command -v node 2>/dev/null); then
    printf '%s\n' "$node_path"
    return 0
  fi

  if [ -n "$user_home" ] && [ -d "$user_home/.cache/codex-runtimes" ]; then
    node_path=$(find "$user_home/.cache/codex-runtimes" \
      -type f \
      -path '*/dependencies/node/bin/node' \
      -perm -111 \
      -print \
      -quit 2>/dev/null || true)
    if [ -n "$node_path" ]; then
      printf '%s\n' "$node_path"
      return 0
    fi
  fi

  return 1
}

validate_local() {
  candidate_commit=$(git -C "$project_dir" rev-parse --short HEAD 2>/dev/null || printf '%s' unknown)
  printf 'Validating local candidate %s\n' "$candidate_commit"

  node_path=''
  if node_path=$(detect_node); then
    printf 'Using Node.js: %s\n' "$node_path"
    NODE_BIN="$node_path" sh "$project_dir/scripts/validate-release.sh"
  else
    printf '%s\n' 'Node.js was not found; the validator will report the JavaScript check as skipped.'
    sh "$project_dir/scripts/validate-release.sh"
  fi
}

validate_router_sample() {
  require_router_tools
  check_worktree

  local_file=$(config_sample_source)
  [ -f "$local_file" ] || die "packaged configuration sample is missing: $local_file"
  [ -r "$local_file" ] || die "packaged configuration sample is not readable: $local_file"

  validate_local
  prepare_stage_dir
  trap cleanup_stage_dir 0 1 2 3 15
  scp_to_router "$local_file" "$remote_stage_dir/config.json.example"
  ssh_router chmod 0600 "$remote_stage_dir/config.json.example"
  ssh_router sh -s <<REMOTE
set -u
sample='$remote_stage_dir/config.json.example'
asset_dir="\$(uci -q get xray-mitm.main.asset_dir 2>/dev/null || true)"
[ -n "\$asset_dir" ] || asset_dir=/usr/share/v2ray
if [ ! -d "\$asset_dir" ]; then
  printf '%s\n' "configured Xray asset directory is missing: \$asset_dir" >&2
  exit 1
fi
set +e
XRAY_LOCATION_ASSET="\$asset_dir" xray run -test -format=json -c "\$sample"
status=\$?
set -e
if [ "\$status" -eq 0 ]; then
  printf '%s\n' 'Router validation of the packaged Xray sample: passed'
else
  printf '%s\n' "Router validation of the packaged Xray sample: failed (exit \$status)" >&2
fi
exit "\$status"
REMOTE
  cleanup_stage_dir
  trap - 0 1 2 3 15
  printf '%s\n' 'The live Xray configuration and service were not changed.'
}

protect_router_originals() {
  printf 'Checking protected router backup: %s\n' "$router_backup_dir"
  ssh_router sh -s <<REMOTE
set -eu
backup_dir='$router_backup_dir'
if [ -f "\$backup_dir/SHA256SUMS" ]; then
  (cd "\$backup_dir" && sha256sum -c SHA256SUMS)
  exit 0
fi
if [ -e "\$backup_dir" ]; then
  printf '%s\n' 'Backup directory exists without a valid SHA256SUMS manifest.' >&2
  exit 1
fi
umask 077
mkdir -p "\$backup_dir"
chmod 0700 "\$backup_dir"
cp -p /usr/libexec/xray-mitm/passwall2 "\$backup_dir/passwall2"
cp -p /usr/sbin/xray-mitmctl "\$backup_dir/xray-mitmctl"
cp -p /usr/share/rpcd/ucode/xray-mitm.uc "\$backup_dir/xray-mitm.uc"
cp -p /www/luci-static/resources/view/xray-mitm/overview.js "\$backup_dir/overview.js"
cp -p /www/luci-static/resources/xray-mitm/state.js "\$backup_dir/state.js"
(cd "\$backup_dir" && sha256sum passwall2 xray-mitmctl xray-mitm.uc overview.js state.js > SHA256SUMS)
chmod 0600 "\$backup_dir/SHA256SUMS"
printf '%s\n' 'Protected the original router files.'
REMOTE
}

prepare_stage_dir() {
  ssh_router sh -s <<REMOTE
set -eu
stage_dir='$remote_stage_dir'
rm -rf "\$stage_dir"
umask 077
mkdir -p "\$stage_dir"
chmod 0700 "\$stage_dir"
REMOTE
}

cleanup_stage_dir() {
  ssh_router rm -rf "$remote_stage_dir" >/dev/null 2>&1 || true
}

verify_remote_file() {
  candidate_name=$1
  local_file=$(candidate_source "$candidate_name")
  remote_file=$2
  expected_hash=$(hash_file "$local_file")
  actual_hash=$(remote_hash "$remote_file")
  [ "$expected_hash" = "$actual_hash" ] || die "hash mismatch for $candidate_name"
  printf 'Verified %s (%s)\n' "$candidate_name" "$actual_hash"
}

stage_candidate() {
  require_router_tools
  validate_backup_dir
  check_worktree

  for candidate_name in $candidate_names; do
    local_file=$(candidate_source "$candidate_name")
    [ -f "$local_file" ] || die "candidate file is missing: $local_file"
    [ -r "$local_file" ] || die "candidate file is not readable: $local_file"
  done

  if [ "${ROUTER_SKIP_VALIDATE:-0}" = 1 ]; then
    printf '%s\n' 'Skipping offline validation by explicit request.'
  else
    validate_local
  fi

  protect_router_originals
  prepare_stage_dir
  trap cleanup_stage_dir 0 1 2 3 15

  for candidate_name in $candidate_names; do
    local_file=$(candidate_source "$candidate_name")
    scp_to_router "$local_file" "$remote_stage_dir/$candidate_name"
  done

  ssh_router chmod 0755 \
    "$remote_stage_dir/passwall2" \
    "$remote_stage_dir/xray-mitmctl"
  ssh_router chmod 0644 \
    "$remote_stage_dir/xray-mitm.uc" \
    "$remote_stage_dir/overview.js" \
    "$remote_stage_dir/state.js"

  for candidate_name in $candidate_names; do
    verify_remote_file "$candidate_name" "$remote_stage_dir/$candidate_name"
  done

  ssh_router sh -s <<REMOTE
set -eu
stage_dir='$remote_stage_dir'
cp -p "\$stage_dir/passwall2" /usr/libexec/xray-mitm/passwall2
cp -p "\$stage_dir/xray-mitmctl" /usr/sbin/xray-mitmctl
cp -p "\$stage_dir/xray-mitm.uc" /usr/share/rpcd/ucode/xray-mitm.uc
cp -p "\$stage_dir/overview.js" /www/luci-static/resources/view/xray-mitm/overview.js
cp -p "\$stage_dir/state.js" /www/luci-static/resources/xray-mitm/state.js
chmod 0755 /usr/libexec/xray-mitm/passwall2 /usr/sbin/xray-mitmctl
chmod 0644 /usr/share/rpcd/ucode/xray-mitm.uc /www/luci-static/resources/view/xray-mitm/overview.js /www/luci-static/resources/xray-mitm/state.js
REMOTE

  for candidate_name in $candidate_names; do
    verify_remote_file "$candidate_name" "$(live_path "$candidate_name")"
  done

  cleanup_stage_dir
  trap - 0 1 2 3 15
  candidate_commit=$(git -C "$project_dir" rev-parse --short HEAD 2>/dev/null || printf '%s' unknown)
  printf 'Staged candidate %s for the real browser test.\n' "$candidate_commit"
  printf '%s\n' 'No service restart, PassWall2 routing apply, or reboot was performed.'
  printf '%s\n' 'Run the browser test, then use this command to restore: sh scripts/router-local-test.sh restore'
}

check_router() {
  require_router_tools
  validate_backup_dir
  printf 'Read-only router check for %s\n' "$router_target"
  ssh_router sh -s <<REMOTE
set -eu
printf '%s\n' '--- service status ---'
xray-mitmctl status-json
printf '%s\n' '--- LuCI setup status ---'
ubus call luci.xray-mitm getSetupStatus
printf '%s\n' '--- live file hashes ---'
sha256sum \
  /usr/libexec/xray-mitm/passwall2 \
  /usr/sbin/xray-mitmctl \
  /usr/share/rpcd/ucode/xray-mitm.uc \
  /www/luci-static/resources/view/xray-mitm/overview.js \
  /www/luci-static/resources/xray-mitm/state.js
if [ -f '$router_backup_dir/SHA256SUMS' ]; then
  printf '%s\n' '--- protected backup verification ---'
  (cd '$router_backup_dir' && sha256sum -c SHA256SUMS)
fi
REMOTE
}

restore_router() {
  require_router_tools
  validate_backup_dir
  printf 'Restoring protected router files from %s\n' "$router_backup_dir"
  ssh_router sh -s <<REMOTE
set -eu
backup_dir='$router_backup_dir'
[ -f "\$backup_dir/SHA256SUMS" ] || {
  printf '%s\n' 'No protected backup manifest was found; refusing to restore.' >&2
  exit 1
}
(cd "\$backup_dir" && sha256sum -c SHA256SUMS)
cp -p "\$backup_dir/passwall2" /usr/libexec/xray-mitm/passwall2
cp -p "\$backup_dir/xray-mitmctl" /usr/sbin/xray-mitmctl
cp -p "\$backup_dir/xray-mitm.uc" /usr/share/rpcd/ucode/xray-mitm.uc
cp -p "\$backup_dir/overview.js" /www/luci-static/resources/view/xray-mitm/overview.js
cp -p "\$backup_dir/state.js" /www/luci-static/resources/xray-mitm/state.js
chmod 0755 /usr/libexec/xray-mitm/passwall2 /usr/sbin/xray-mitmctl
chmod 0644 /usr/share/rpcd/ucode/xray-mitm.uc /www/luci-static/resources/view/xray-mitm/overview.js /www/luci-static/resources/xray-mitm/state.js
printf '%s\n' 'Restored protected router files. No service restart or routing change was performed.'
REMOTE
}

command_name=${1:-help}
case "$command_name" in
  validate) validate_local ;;
  config-validate) validate_router_sample ;;
  stage) stage_candidate ;;
  check) check_router ;;
  restore) restore_router ;;
  help|-h|--help) usage ;;
  *) usage >&2; exit 2 ;;
esac
