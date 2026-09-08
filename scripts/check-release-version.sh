#!/bin/sh
set -eu

project_dir="${1:-$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)}"
release_tag="${2:-${GITHUB_REF_NAME:-}}"

[ -n "$release_tag" ] || {
	printf 'ERROR: release tag is required.\n' >&2
	exit 1
}

version="$(sed -n 's/^PKG_VERSION:=//p' "$project_dir/xray-mitm/Makefile")"
release="$(sed -n 's/^PKG_RELEASE:=//p' "$project_dir/xray-mitm/Makefile")"

[ -n "$version" ] && [ -n "$release" ] || {
	printf 'ERROR: package version is incomplete.\n' >&2
	exit 1
}

[ "$release_tag" = "v$version" ] || {
	printf 'ERROR: tag %s does not match PKG_VERSION %s.\n' "$release_tag" "$version" >&2
	exit 1
}

[ "$release" = '1' ] || {
	printf 'ERROR: a new version tag must start with PKG_RELEASE 1, found %s.\n' "$release" >&2
	exit 1
}

printf 'Release version verified: %s (package release r%s)\n' "$release_tag" "$release"
