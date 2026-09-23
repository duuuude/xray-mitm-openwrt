#!/bin/sh
set -eu

backup_dir=${1:-}
operation=${2:-}
stage_dir=${3:-}
filesystem_root=${ROUTER_GUARD_ROOT:-/}

die() {
  printf 'router-backup-guard: %s\n' "$*" >&2
  exit 1
}

stat_metadata() {
  metadata=$(stat -c '%u %a' "$1" 2>/dev/null) || \
    metadata=$(stat -f '%u %Lp' "$1" 2>/dev/null) || \
    die "cannot inspect ownership and permissions for $1"
  printf '%s\n' "$metadata"
}
[ -n "$backup_dir" ] || die 'backup directory argument is required'
case "$backup_dir" in
  /*) ;;
  *) die 'backup directory must be an absolute path' ;;
esac
case "$backup_dir" in
  *[!A-Za-z0-9_./-]*) die 'backup directory contains an unsafe character' ;;
esac
case "/$backup_dir/" in
  */../*) die 'backup directory may not contain a parent-directory component' ;;
  */./*) die 'backup directory may not contain a current-directory component' ;;
esac
while [ "$backup_dir" != / ] && [ "${backup_dir%/}" != "$backup_dir" ]; do
  backup_dir=${backup_dir%/}
done
[ "$backup_dir" != / ] || die 'backup directory may not be the filesystem root'
case "$filesystem_root" in
  /*) ;;
  *) die 'ROUTER_GUARD_ROOT must be an absolute path' ;;
esac
if [ "$filesystem_root" != / ]; then
  filesystem_root=${filesystem_root%/}
fi

trusted_root=$filesystem_root
[ -d "$trusted_root" ] && [ ! -L "$trusted_root" ] || die 'ROUTER_GUARD_ROOT must be an existing real directory'
root_metadata=$(stat_metadata "$trusted_root")
set -- $root_metadata
[ "$#" -eq 2 ] || die 'cannot parse filesystem-root ownership and permissions'
trusted_owner_uid=$1
root_mode=$2
if [ "$trusted_root" = / ]; then
  [ "$trusted_owner_uid" = 0 ] || die 'filesystem root is not owned by root'
  trusted_owner_uid=0
fi
root_write_bits=$((0$root_mode & 0022))
[ "$root_write_bits" -eq 0 ] || die 'filesystem root is group/other writable; refusing to trust it'
live_path() {
  case "$1" in
    passwall2) relative_path=/usr/libexec/xray-mitm/passwall2 ;;
    xray-mitmctl) relative_path=/usr/sbin/xray-mitmctl ;;
    xray-mitm.uc) relative_path=/usr/share/rpcd/ucode/xray-mitm.uc ;;
    overview.js) relative_path=/www/luci-static/resources/view/xray-mitm/overview.js ;;
    state.js) relative_path=/www/luci-static/resources/xray-mitm/state.js ;;
    ui.js) relative_path=/www/luci-static/resources/xray-mitm/ui.js ;;
    *) die "unknown file name: $1" ;;
  esac
  if [ "$filesystem_root" = / ]; then
    printf '%s\n' "$relative_path"
  else
    printf '%s%s\n' "$filesystem_root" "$relative_path"
  fi
}

is_regular_file() {
  [ -f "$1" ] && [ ! -L "$1" ]
}

validate_protected_directory() {
  directory_path=$1
  [ -d "$directory_path" ] && [ ! -L "$directory_path" ] || \
    die "protected path component is missing, not a directory, or a symlink: $directory_path"
  directory_metadata=$(stat_metadata "$directory_path")
  set -- $directory_metadata
  [ "$#" -eq 2 ] || die "cannot parse directory ownership and permissions: $directory_path"
  [ "$1" = "$trusted_owner_uid" ] || \
    die "protected directory is not owned by trusted uid $trusted_owner_uid: $directory_path"
  directory_write_bits=$((0$2 & 0022))
  [ "$directory_write_bits" -eq 0 ] || \
    die "protected directory is group/other writable: $directory_path"
}

validate_backup_parent_path() {
  backup_parent=${backup_dir%/*}
  [ -n "$backup_parent" ] || backup_parent=/

  if [ "$trusted_root" = / ]; then
    relative_parent=${backup_parent#/}
    current_directory=/
  else
    case "$backup_dir" in
      "$trusted_root"/*) ;;
      *) die 'backup path must remain beneath ROUTER_GUARD_ROOT in test mode' ;;
    esac
    case "$backup_parent" in
      "$trusted_root") relative_parent= ;;
      "$trusted_root"/*) relative_parent=${backup_parent#"$trusted_root"/} ;;
      *) die 'backup parent path escapes ROUTER_GUARD_ROOT' ;;
    esac
    current_directory=$trusted_root
  fi

  validate_protected_directory "$current_directory"
  old_ifs=$IFS
  IFS=/
  set -- $relative_parent
  IFS=$old_ifs
  for directory_component do
    [ -n "$directory_component" ] || continue
    if [ "$current_directory" = / ]; then
      current_directory=/$directory_component
    else
      current_directory=$current_directory/$directory_component
    fi
    validate_protected_directory "$current_directory"
  done
}

validate_protected_backup_tree() {
  validate_backup_parent_path
  validate_protected_directory "$backup_dir"

  for backup_entry in "$backup_dir"/* "$backup_dir"/.[!.]* "$backup_dir"/..?*; do
    if [ ! -e "$backup_entry" ] && [ ! -L "$backup_entry" ]; then
      continue
    fi
    is_regular_file "$backup_entry" || \
      die "protected backup contains a symlink or non-regular entry: $backup_entry"
    entry_metadata=$(stat_metadata "$backup_entry")
    set -- $entry_metadata
    [ "$#" -eq 2 ] || die "cannot parse backup-file ownership and permissions: $backup_entry"
    [ "$1" = "$trusted_owner_uid" ] || \
      die "protected backup file is not owned by trusted uid $trusted_owner_uid: $backup_entry"
    entry_write_bits=$((0$2 & 0022))
    [ "$entry_write_bits" -eq 0 ] || \
      die "protected backup file is group/other writable: $backup_entry"
    case "${backup_entry##*/}" in
      passwall2|xray-mitmctl|xray-mitm.uc|overview.js|state.js|ui.js|ui.js.absent|SHA256SUMS|ACTIVE_STAGE) ;;
      *) die "protected backup contains an unexpected entry: ${backup_entry##*/}" ;;
    esac
  done
}
hash_file() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk 'NR == 1 { print $1 }'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk 'NR == 1 { print $1 }'
  else
    die 'sha256sum or shasum is required'
  fi
}

write_checksum_manifest() {
  manifest_dir=$1
  (
    cd "$manifest_dir"
    if command -v sha256sum >/dev/null 2>&1; then
      if [ -f ui.js ]; then
        sha256sum passwall2 xray-mitmctl xray-mitm.uc overview.js state.js ui.js
      else
        sha256sum passwall2 xray-mitmctl xray-mitm.uc overview.js state.js ui.js.absent
      fi
    elif command -v shasum >/dev/null 2>&1; then
      if [ -f ui.js ]; then
        shasum -a 256 passwall2 xray-mitmctl xray-mitm.uc overview.js state.js ui.js
      else
        shasum -a 256 passwall2 xray-mitmctl xray-mitm.uc overview.js state.js ui.js.absent
      fi
    else
      die 'sha256sum or shasum is required'
    fi
  ) > "$manifest_dir/SHA256SUMS"
  chmod 0600 "$manifest_dir/SHA256SUMS"
}

verify_checksum_manifest() {
  if command -v sha256sum >/dev/null 2>&1; then
    (cd "$backup_dir" && sha256sum -c SHA256SUMS)
  elif command -v shasum >/dev/null 2>&1; then
    (cd "$backup_dir" && shasum -a 256 -c SHA256SUMS)
  else
    die 'sha256sum or shasum is required'
  fi
}

manifest_digest() {
  manifest_path=$1
  manifest_name=$2
  awk -v wanted="$manifest_name" \
    '$2 == wanted { count++; digest = $1 } END { if (count != 1) exit 1; print digest }' \
    "$manifest_path"
}

expected_backup_names() {
  printf '%s\n' passwall2 xray-mitmctl xray-mitm.uc overview.js state.js
  if [ -f "$backup_dir/ui.js" ]; then
    printf '%s\n' ui.js
  elif [ -f "$backup_dir/ui.js.absent" ]; then
    printf '%s\n' ui.js.absent
  fi
}

validate_backup_manifest() {
  validate_protected_backup_tree
  is_regular_file "$backup_dir/SHA256SUMS" || die 'protected backup checksum manifest is missing or unsafe'

  for backup_name in passwall2 xray-mitmctl xray-mitm.uc overview.js state.js; do
    is_regular_file "$backup_dir/$backup_name" || die "protected backup is missing a regular $backup_name file"
  done

  if [ -f "$backup_dir/ui.js" ]; then
    [ ! -e "$backup_dir/ui.js.absent" ] && [ ! -L "$backup_dir/ui.js.absent" ] || die 'protected backup has conflicting ui.js presence markers'
    is_regular_file "$backup_dir/ui.js" || die 'protected backup ui.js is unsafe'
  elif [ -f "$backup_dir/ui.js.absent" ]; then
    [ ! -e "$backup_dir/ui.js" ] && [ ! -L "$backup_dir/ui.js" ] || die 'protected backup has conflicting ui.js presence markers'
    is_regular_file "$backup_dir/ui.js.absent" || die 'protected backup ui.js absence marker is unsafe'
    [ ! -s "$backup_dir/ui.js.absent" ] || die 'protected backup ui.js absence marker must be empty'
  else
    die 'protected backup has no ui.js file or absence marker'
  fi

  actual_backup_names=$(awk 'NF >= 2 { print $2 }' "$backup_dir/SHA256SUMS" | LC_ALL=C sort)
  expected_names=$(expected_backup_names | LC_ALL=C sort)
  [ "$actual_backup_names" = "$expected_names" ] || die 'protected backup manifest has an unexpected or incomplete file set'
  verify_checksum_manifest
}

verify_backup_matches_live() {
  for backup_name in passwall2 xray-mitmctl xray-mitm.uc overview.js state.js; do
    live_file=$(live_path "$backup_name")
    is_regular_file "$live_file" || die "live $backup_name is missing or is not a regular file; refusing to stage or restore"
    backup_digest=$(hash_file "$backup_dir/$backup_name")
    live_digest=$(hash_file "$live_file")
    [ "$backup_digest" = "$live_digest" ] || die "saved backup is stale for $backup_name; refusing to stage or restore"
  done

  live_ui=$(live_path ui.js)
  if [ -f "$backup_dir/ui.js" ]; then
    is_regular_file "$live_ui" || die 'saved backup expects ui.js, but the live file is missing or unsafe'
    backup_digest=$(hash_file "$backup_dir/ui.js")
    live_digest=$(hash_file "$live_ui")
    [ "$backup_digest" = "$live_digest" ] || die 'saved backup is stale for ui.js; refusing to stage or restore'
  else
    [ ! -e "$live_ui" ] && [ ! -L "$live_ui" ] || die 'saved backup marks ui.js absent, but the live file exists; refusing to stage or restore'
  fi
}

make_initial_backup() {
  for source_name in passwall2 xray-mitmctl xray-mitm.uc overview.js state.js; do
    source_file=$(live_path "$source_name")
    is_regular_file "$source_file" || die "cannot capture missing or unsafe live $source_name"
  done
  source_ui=$(live_path ui.js)
  if { [ -e "$source_ui" ] || [ -L "$source_ui" ]; } && ! is_regular_file "$source_ui"; then
    die 'cannot capture unsafe live ui.js'
  fi

  backup_parent=${backup_dir%/*}
  backup_name=${backup_dir##*/}
  [ -n "$backup_parent" ] || backup_parent=/
  [ ! -e "$backup_dir" ] && [ ! -L "$backup_dir" ] || die 'backup directory appeared during capture; refusing to overwrite it'
  validate_backup_parent_path
  capture_dir=$backup_parent/.${backup_name}.new.$$
  [ ! -e "$capture_dir" ] && [ ! -L "$capture_dir" ] || die 'temporary backup path already exists; refusing to overwrite it'
  umask 077
  mkdir "$capture_dir"
  chmod 0700 "$capture_dir"
  cleanup_capture() {
    if [ -n "${capture_dir:-}" ] && [ -d "$capture_dir" ]; then
      rm -rf "$capture_dir"
    fi
  }
  trap cleanup_capture 0
  trap 'cleanup_capture; exit 1' 1 2 3 15

  for source_name in passwall2 xray-mitmctl xray-mitm.uc overview.js state.js; do
    cp -p "$(live_path "$source_name")" "$capture_dir/$source_name"
  done
  if is_regular_file "$source_ui"; then
    cp -p "$source_ui" "$capture_dir/ui.js"
    chmod 0600 "$capture_dir/ui.js"
  else
    : > "$capture_dir/ui.js.absent"
    chmod 0600 "$capture_dir/ui.js.absent"
  fi
  write_checksum_manifest "$capture_dir"
  [ ! -e "$backup_dir" ] && [ ! -L "$backup_dir" ] || die 'backup directory appeared during capture; refusing to replace it'
  mv "$capture_dir" "$backup_dir"
  capture_dir=''
  trap - 0 1 2 3 15
  chmod 0700 "$backup_dir"
  printf '%s\n' 'Captured a new protected baseline from the current live files.'
}

active_manifest=$backup_dir/ACTIVE_STAGE

validate_active_manifest() {
  is_regular_file "$active_manifest" || die 'active staged-candidate manifest is missing or unsafe'
  actual_stage_names=$(awk 'NF >= 2 { print $2 }' "$active_manifest" | LC_ALL=C sort)
  expected_stage_names=$(printf '%s\n' passwall2 xray-mitmctl xray-mitm.uc overview.js state.js ui.js | LC_ALL=C sort)
  [ "$actual_stage_names" = "$expected_stage_names" ] || die 'active staged-candidate manifest has an unexpected or incomplete file set'
  awk 'NF != 2 { bad = 1 } END { exit bad }' "$active_manifest" || die 'active staged-candidate manifest is malformed'

  for candidate_name in passwall2 xray-mitmctl xray-mitm.uc overview.js state.js ui.js; do
    candidate_digest=$(manifest_digest "$active_manifest" "$candidate_name") || die "active staged-candidate manifest has duplicate or missing $candidate_name"
    case "$candidate_digest" in
      *[!0123456789abcdefABCDEF]*) die "active staged-candidate digest is invalid for $candidate_name" ;;
    esac
    [ "${#candidate_digest}" -eq 64 ] || die "active staged-candidate digest has the wrong length for $candidate_name"
  done
}

backup_digest_for() {
  backup_name=$1
  if [ "$backup_name" = ui.js ] && [ -f "$backup_dir/ui.js.absent" ]; then
    printf '%s\n' ABSENT
  else
    manifest_digest "$backup_dir/SHA256SUMS" "$backup_name"
  fi
}

verify_live_is_known_stage_state() {
  for candidate_name in passwall2 xray-mitmctl xray-mitm.uc overview.js state.js ui.js; do
    live_file=$(live_path "$candidate_name")
    baseline_digest=$(backup_digest_for "$candidate_name") || die "protected backup has no baseline digest for $candidate_name"
    candidate_digest=$(manifest_digest "$active_manifest" "$candidate_name") || die "active staged-candidate manifest has no digest for $candidate_name"

    if [ -e "$live_file" ] || [ -L "$live_file" ]; then
      is_regular_file "$live_file" || die "live $candidate_name is not a regular file; refusing to overwrite unknown state"
      live_digest=$(hash_file "$live_file")
      [ "$live_digest" = "$baseline_digest" ] || [ "$live_digest" = "$candidate_digest" ] || die "live $candidate_name matches neither saved baseline nor staged candidate; refusing to overwrite unknown state"
    else
      [ "$baseline_digest" = ABSENT ] || die "live $candidate_name is absent unexpectedly; refusing to overwrite unknown state"
    fi
  done
}

protect_router_files() {
  [ ! -e "$active_manifest" ] && [ ! -L "$active_manifest" ] || die 'an earlier staged candidate is still active; restore it before staging another candidate'
  if [ -e "$backup_dir" ] || [ -L "$backup_dir" ]; then
    validate_backup_manifest
    verify_backup_matches_live
    printf '%s\n' 'Existing protected baseline exactly matches the current live files.'
  else
    make_initial_backup
    validate_backup_manifest
    verify_backup_matches_live
  fi
}

arm_staged_candidate() {
  [ -n "$stage_dir" ] || die 'stage directory argument is required for arm'
  [ -d "$stage_dir" ] && [ ! -L "$stage_dir" ] || die 'staged candidate directory is missing or unsafe'
  [ ! -e "$active_manifest" ] && [ ! -L "$active_manifest" ] || die 'an active staged-candidate manifest already exists'
  validate_backup_manifest
  verify_backup_matches_live

  for candidate_name in passwall2 xray-mitmctl xray-mitm.uc overview.js state.js ui.js; do
    is_regular_file "$stage_dir/$candidate_name" || die "staged candidate is missing or unsafe: $candidate_name"
  done

  active_temp=$backup_dir/.ACTIVE_STAGE.$$
  [ ! -e "$active_temp" ] && [ ! -L "$active_temp" ] || die 'temporary staged manifest already exists; refusing to overwrite it'
  (
    cd "$stage_dir"
    if command -v sha256sum >/dev/null 2>&1; then
      sha256sum passwall2 xray-mitmctl xray-mitm.uc overview.js state.js ui.js
    elif command -v shasum >/dev/null 2>&1; then
      shasum -a 256 passwall2 xray-mitmctl xray-mitm.uc overview.js state.js ui.js
    else
      die 'sha256sum or shasum is required'
    fi
  ) > "$active_temp"
  chmod 0600 "$active_temp"
  [ ! -e "$active_manifest" ] && [ ! -L "$active_manifest" ] || die 'active staged-candidate manifest appeared during arming'
  mv "$active_temp" "$active_manifest"
  chmod 0600 "$active_manifest"
  validate_active_manifest
  printf '%s\n' 'Armed an exact staged-candidate hash manifest before touching live files.'
}

restore_staged_candidate() {
  validate_backup_manifest
  validate_active_manifest
  verify_live_is_known_stage_state

  temporary_file=''
  cleanup_restore_temporary() {
    if [ -n "$temporary_file" ]; then
      rm -f "$temporary_file"
    fi
  }
  trap cleanup_restore_temporary 0
  trap 'cleanup_restore_temporary; exit 1' 1 2 3 15
  restore_file_atomically() {
    source_file=$1
    destination_file=$2
    file_mode=$3
    temporary_file=$(mktemp "$destination_file.xray-mitm-restore.XXXXXX")
    cp -p "$source_file" "$temporary_file"
    chmod "$file_mode" "$temporary_file"
    mv -f "$temporary_file" "$destination_file"
    temporary_file=''
  }

  for restore_name in passwall2 xray-mitmctl xray-mitm.uc overview.js state.js; do
    if [ "$restore_name" = passwall2 ] || [ "$restore_name" = xray-mitmctl ]; then
      restore_mode=0755
    else
      restore_mode=0644
    fi
    restore_file_atomically "$backup_dir/$restore_name" "$(live_path "$restore_name")" "$restore_mode"
  done
  if [ -f "$backup_dir/ui.js" ]; then
    restore_file_atomically "$backup_dir/ui.js" "$(live_path ui.js)" 0644
  else
    rm -f "$(live_path ui.js)"
  fi

  verify_backup_matches_live
  trap - 0 1 2 3 15
  rm -f "$active_manifest"
  printf '%s\n' 'Restored exact protected originals; no service restart or routing change was performed.'
}

check_router_state() {
  if [ ! -e "$backup_dir" ] && [ ! -L "$backup_dir" ]; then
    printf '%s\n' 'No protected local-test baseline exists yet.'
    return 0
  fi
  validate_backup_manifest
  if [ -e "$active_manifest" ] || [ -L "$active_manifest" ]; then
    validate_active_manifest
    verify_live_is_known_stage_state
    printf '%s\n' 'Active staged-test state matches only the saved baseline and/or exact staged candidate.'
  else
    verify_backup_matches_live
    printf '%s\n' 'No staged test is active; protected baseline exactly matches live files.'
  fi
}

case "$operation" in
  protect) protect_router_files ;;
  arm) arm_staged_candidate ;;
  restore) restore_staged_candidate ;;
  check) check_router_state ;;
  *) die 'operation must be protect, arm, restore, or check' ;;
esac
