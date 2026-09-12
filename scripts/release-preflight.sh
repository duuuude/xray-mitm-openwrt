#!/bin/sh
set -eu

project_dir="${1:-$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)}"
github_remote="${RELEASE_GITHUB_REMOTE:-github}"
makefile="$project_dir/xray-mitm/Makefile"
changelog="$project_dir/CHANGELOG.md"
validate_command="${RELEASE_PREFLIGHT_VALIDATE_CMD:-$project_dir/scripts/validate-release.sh}"

say() {
	printf '%s\n' "$*"
}

die() {
	printf 'ERROR: %s\n' "$*" >&2
	exit 1
}

git_at() {
	git -C "$project_dir" "$@"
}

[ -d "$project_dir" ] || die "Project directory does not exist: $project_dir"
[ -f "$makefile" ] || die 'xray-mitm/Makefile is missing.'
[ -f "$changelog" ] || die 'CHANGELOG.md is missing.'
[ -f "$validate_command" ] || die "Validation script is missing: $validate_command"

branch="$(git_at symbolic-ref --quiet --short HEAD 2>/dev/null || true)"
[ "$branch" = 'main' ] || die "Release preflight must run on main; current branch is ${branch:-detached HEAD}."

[ -z "$(git_at status --porcelain --untracked-files=all)" ] || die 'The main worktree is not clean.'

remote_url="$(git_at config --get "remote.$github_remote.url" 2>/dev/null || true)"
case "$remote_url" in
	https://github.com/duuuude/xray-mitm-openwrt|https://github.com/duuuude/xray-mitm-openwrt.git|git@github.com:duuuude/xray-mitm-openwrt|git@github.com:duuuude/xray-mitm-openwrt.git|ssh://git@github.com/duuuude/xray-mitm-openwrt|ssh://git@github.com/duuuude/xray-mitm-openwrt.git)
		;;
	'')
		die "Verified GitHub remote '$github_remote' was not found."
		;;
	*)
		die "Remote '$github_remote' is not the verified duuuude/xray-mitm-openwrt GitHub repository."
		;;
esac

if ! git_at fetch --quiet --no-tags "$github_remote" "refs/heads/main:refs/remotes/$github_remote/main"; then
	die "Could not fetch main from verified GitHub remote '$github_remote'."
fi

local_head="$(git_at rev-parse --verify refs/heads/main 2>/dev/null || true)"
head="$(git_at rev-parse --verify HEAD 2>/dev/null || true)"
remote_head="$(git_at rev-parse --verify "refs/remotes/$github_remote/main" 2>/dev/null || true)"
[ -n "$local_head" ] && [ "$head" = "$local_head" ] || die 'HEAD is not the local main branch tip.'
[ -n "$remote_head" ] && [ "$local_head" = "$remote_head" ] || die "Local main is not synchronized with '$github_remote/main'."

version="$(sed -n 's/^PKG_VERSION:=//p' "$makefile" | head -n 1)"
release="$(sed -n 's/^PKG_RELEASE:=//p' "$makefile" | head -n 1)"
[ -n "$version" ] && [ -n "$release" ] || die 'Package version is incomplete.'
[ "$release" = '1' ] || die "PKG_RELEASE must be 1 for a new version tag; found $release."

case "$version" in
	*[!0-9.]*|.*|*.)
		die "PKG_VERSION is not a numeric semantic version: $version"
		;;
esac
printf '%s\n' "$version" | awk -F. 'NF == 3 && $1 ~ /^[0-9]+$/ && $2 ~ /^[0-9]+$/ && $3 ~ /^[0-9]+$/ { found = 1 } END { exit(found ? 0 : 1) }' || die "PKG_VERSION must have three numeric components: $version"

tag="v$version"
dated_heading="$(awk -v prefix="## [$version] - " '
	index($0, prefix) == 1 {
		date = substr($0, length(prefix) + 1)
		if (date ~ /^[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]$/) {
			print $0
			exit
		}
	}
' "$changelog")"
[ -n "$dated_heading" ] || die "CHANGELOG.md has no dated section for $tag."

sh "$project_dir/scripts/release-notes.sh" "$project_dir" "$tag" >/dev/null || die "CHANGELOG.md has no release notes for $tag."

grep -Fqx '## [Unreleased]' "$changelog" || die 'CHANGELOG.md is missing the Unreleased section.'
unreleased_notes="$(awk '
	$0 == "## [Unreleased]" { in_unreleased = 1; next }
	in_unreleased && /^## \[/ { exit }
	in_unreleased { print }
' "$changelog" | sed '/^[[:space:]]*$/d')"
[ -z "$unreleased_notes" ] || die 'CHANGELOG.md still contains entries under Unreleased; move them into the dated release section first.'

if git_at show-ref --verify --quiet "refs/tags/$tag"; then
	die "Tag $tag already exists locally."
fi

remote_tag_status=0
git_at ls-remote --exit-code --refs "$github_remote" "refs/tags/$tag" >/dev/null 2>&1 || remote_tag_status=$?
case "$remote_tag_status" in
	0) die "Tag $tag already exists on '$github_remote'." ;;
	2) ;;
	*) die "Could not query tags on verified GitHub remote '$github_remote'." ;;
esac

if ! sh "$validate_command"; then
	die 'Full release validation failed.'
fi

say 'Release preflight passed.'
say "Ready to sign: $tag"
