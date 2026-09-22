#!/bin/sh
set -eu

usage() {
	printf '%s\n' 'Usage: scripts/verify-github-remote.sh [remote]' >&2
	exit 2
}

die() {
	printf 'ROADMAP_STATE=BLOCKED\nERROR: %s\n' "$*" >&2
	exit 1
}

[ "$#" -le 1 ] || usage

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
project_dir=$(CDPATH= cd -- "$script_dir/.." && pwd -P)
remote_name=${1:-origin}

git_at() {
	git -C "$project_dir" "$@"
}

is_verified_remote() {
	case "$1" in
		https://github.com/duuuude/xray-mitm-openwrt|https://github.com/duuuude/xray-mitm-openwrt.git|git@github.com:duuuude/xray-mitm-openwrt|git@github.com:duuuude/xray-mitm-openwrt.git|ssh://git@github.com/duuuude/xray-mitm-openwrt|ssh://git@github.com/duuuude/xray-mitm-openwrt.git)
			return 0
			;;
		*)
			return 1
			;;
	esac
}

[ -d "$project_dir" ] || die "Project directory does not exist: $project_dir"
git_root=$(git_at rev-parse --show-toplevel 2>/dev/null) || die 'Could not inspect the Git repository root.'
[ "$git_root" = "$project_dir" ] || die 'The helper must run from the canonical repository checkout.'

fetch_urls=$(git_at remote get-url --all "$remote_name" 2>/dev/null) || die "Could not resolve effective fetch URL(s) for remote '$remote_name'."
[ -n "$fetch_urls" ] || die "Remote '$remote_name' has no effective fetch URL."
for fetch_url in $fetch_urls; do
	is_verified_remote "$fetch_url" || die "Remote '$remote_name' has an unverified effective fetch URL."
done

push_urls=$(git_at remote get-url --push --all "$remote_name" 2>/dev/null) || die "Could not resolve effective push URL(s) for remote '$remote_name'."
[ -n "$push_urls" ] || die "Remote '$remote_name' has no effective push URL."
for push_url in $push_urls; do
	is_verified_remote "$push_url" || die "Remote '$remote_name' has an unverified effective push URL."
done

printf 'GITHUB_REMOTE=VERIFIED\n'
printf 'Remote: %s\n' "$remote_name"
printf '%s\n' 'Effective fetch URL(s):'
printf '  %s\n' $fetch_urls
printf '%s\n' 'Effective push URL(s):'
printf '  %s\n' $push_urls
