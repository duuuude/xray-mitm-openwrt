#!/bin/sh
set -eu

project_dir="${1:-$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)}"
release_tag="${2:-${GITHUB_REF_NAME:-}}"

[ -n "$release_tag" ] || {
	printf 'ERROR: release tag is required.\n' >&2
	exit 1
}

version="${release_tag#v}"
[ "$version" != "$release_tag" ] || {
	printf 'ERROR: release tag must start with v.\n' >&2
	exit 1
}

changelog="$project_dir/CHANGELOG.md"
[ -f "$changelog" ] || {
	printf 'ERROR: CHANGELOG.md is missing.\n' >&2
	exit 1
}

notes="$(awk -v heading="## [$version]" '
	$0 == heading || index($0, heading " - ") == 1 { found = 1; next }
	found && /^## \[/ { exit }
	found { print }
' "$changelog")"

[ -n "$(printf '%s\n' "$notes" | sed '/^[[:space:]]*$/d')" ] || {
	printf 'ERROR: CHANGELOG.md has no notes for %s.\n' "$release_tag" >&2
	exit 1
}

printf '%s\n' "$notes"
