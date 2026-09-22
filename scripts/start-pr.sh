#!/bin/sh
set -eu

usage() {
	printf '%s\n' 'Usage: scripts/start-pr.sh <branch-name> <workspace-root>/worktrees/<task>' >&2
	exit 2
}

say() {
	printf '%s\n' "$*"
}

die() {
	printf 'ERROR: %s\n' "$*" >&2
	exit 1
}

[ "$#" -eq 2 ] || usage

branch_name="$1"
worktree_path="${2%/}"

case "$branch_name" in
	''|main|-*)
		die 'Feature branch name must be non-empty, must not be main, and must not start with a dash.'
		;;
esac

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
project_dir=$(CDPATH= cd -- "$script_dir/.." && pwd -P)
workspace_root=$(CDPATH= cd -- "$project_dir/.." && pwd -P)
worktrees_root="$workspace_root/worktrees"

git_at() {
	git -C "$project_dir" "$@"
}

[ -d "$project_dir" ] || die "Project directory does not exist: $project_dir"

git_root="$(git_at rev-parse --show-toplevel 2>/dev/null || true)"
[ "$git_root" = "$project_dir" ] || die 'The helper must run from the canonical repository checkout.'

git_at check-ref-format --branch "$branch_name" >/dev/null 2>&1 || die "Invalid feature branch name: $branch_name"

current_branch="$(git_at symbolic-ref --quiet --short HEAD 2>/dev/null || true)"
[ "$current_branch" = 'main' ] || die "The canonical checkout must be on main; current branch is ${current_branch:-detached HEAD}."

main_status="$(git_at status --porcelain --untracked-files=all)" || die 'Could not inspect the canonical main status.'
[ -z "$main_status" ] || die 'The canonical main checkout is not clean.'

case "$worktree_path" in
	/*)
		;;
	*)
		die 'Worktree path must be absolute.'
		;;
esac

case "/$worktree_path/" in
	*'/../'*|*'/./'*)
		die 'Worktree path must not contain dot or dot-dot path components.'
		;;
esac

worktree_parent="${worktree_path%/*}"
worktree_name="${worktree_path##*/}"
[ "$worktree_parent" != "$worktree_path" ] && [ -n "$worktree_name" ] || die 'Worktree path must name one child directory.'

[ ! -L "$worktrees_root" ] || die "The worktrees root must not be a symlink: $worktrees_root"
if [ -e "$worktrees_root" ] && [ ! -d "$worktrees_root" ]; then
	die "The worktrees root is not a directory: $worktrees_root"
fi
[ ! -L "$worktree_parent" ] || die "The requested worktrees parent must not be a symlink: $worktree_parent"

worktree_parent_base="${worktree_parent%/*}"
worktree_parent_name="${worktree_parent##*/}"
[ -n "$worktree_parent_base" ] && [ -n "$worktree_parent_name" ] || die 'Worktree path must name a direct child of the worktrees root.'

canonical_parent_base="$(CDPATH= cd -- "$worktree_parent_base" 2>/dev/null && pwd -P)" || die 'The worktree path parent could not be resolved.'
canonical_worktree_parent="$canonical_parent_base/$worktree_parent_name"
[ "$canonical_worktree_parent" = "$worktrees_root" ] || die "Worktree must be created directly under $worktrees_root."

if [ -e "$worktrees_root" ]; then
	canonical_worktrees_root="$(CDPATH= cd -- "$worktrees_root" 2>/dev/null && pwd -P)" || die 'The worktrees root could not be resolved.'
	[ "$canonical_worktrees_root" = "$worktrees_root" ] || die "The worktrees root must not resolve outside $worktrees_root."
fi

canonical_worktree_path="$worktrees_root/$worktree_name"
[ ! -e "$canonical_worktree_path" ] && [ ! -L "$canonical_worktree_path" ] || die "Worktree path already exists: $canonical_worktree_path"

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

verified_remote="${START_PR_REMOTE:-}"
if [ -n "$verified_remote" ]; then
	remote_url="$(git_at config --get-all "remote.$verified_remote.url" 2>/dev/null || true)"
	[ -n "$remote_url" ] || die "Configured remote '$verified_remote' was not found."
	is_verified_remote "$remote_url" || die "Remote '$verified_remote' is not the verified duuuude/xray-mitm-openwrt GitHub repository."
else
	verified_count=0
	for candidate_remote in $(git_at remote); do
		candidate_url="$(git_at config --get-all "remote.$candidate_remote.url" 2>/dev/null || true)"
		if is_verified_remote "$candidate_url"; then
			verified_remote="$candidate_remote"
			verified_count=$((verified_count + 1))
		fi
	done
	if [ "$verified_count" -eq 0 ]; then
		die 'No verified duuuude/xray-mitm-openwrt GitHub remote was found.'
	elif [ "$verified_count" -gt 1 ]; then
		die 'More than one verified GitHub remote was found; set START_PR_REMOTE to resolve the ambiguity.'
	fi
	remote_url="$(git_at config --get-all "remote.$verified_remote.url")"
fi

push_url="$(git_at config --get-all "remote.$verified_remote.pushurl" 2>/dev/null || true)"
[ -n "$push_url" ] || push_url="$remote_url"
is_verified_remote "$push_url" || die "Push URL for remote '$verified_remote' is not the verified duuuude/xray-mitm-openwrt GitHub repository."

upstream="$(git_at rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' 2>/dev/null || true)"
[ "$upstream" = "$verified_remote/main" ] || die "Local main must track '$verified_remote/main'; found ${upstream:-no upstream}."

if ! git_at fetch --quiet --no-tags "$verified_remote" "refs/heads/main:refs/remotes/$verified_remote/main"; then
	die "Could not fetch main from verified GitHub remote '$verified_remote'."
fi

local_main="$(git_at rev-parse --verify refs/heads/main 2>/dev/null || true)"
remote_main="$(git_at rev-parse --verify "refs/remotes/$verified_remote/main" 2>/dev/null || true)"
[ -n "$local_main" ] || die 'The local main branch does not exist.'
[ -n "$remote_main" ] || die "The verified remote '$verified_remote/main' does not exist."

if [ "$local_main" != "$remote_main" ]; then
	if git_at merge-base --is-ancestor "$local_main" "$remote_main"; then
		git_at merge --ff-only "refs/remotes/$verified_remote/main" >/dev/null || die 'Could not fast-forward local main safely.'
	else
		die "Local main is ahead of or diverged from '$verified_remote/main'; refusing to overwrite unique work."
	fi
fi

main_status="$(git_at status --porcelain --untracked-files=all)" || die 'Could not recheck the canonical main status after synchronization.'
[ -z "$main_status" ] || die 'The canonical main checkout became dirty during synchronization.'
base_commit="$(git_at rev-parse --verify refs/heads/main)"
[ ! -L "$worktrees_root" ] || die "The worktrees root became a symlink: $worktrees_root"

if [ -f "$project_dir/docs/ai/MASTER_PLAN.md" ] && [ -f "$project_dir/scripts/verify-roadmap-state.sh" ]; then
	sh "$project_dir/scripts/verify-roadmap-state.sh" "$verified_remote" || \
		die 'Current main and MASTER_PLAN.md are not reconciled; refusing to start new PR work.'
fi

mkdir -p "$worktrees_root"
canonical_worktrees_root="$(CDPATH= cd -- "$worktrees_root" 2>/dev/null && pwd -P)" || die 'The worktrees root could not be resolved after synchronization.'
[ "$canonical_worktrees_root" = "$worktrees_root" ] || die "The worktrees root must not resolve outside $worktrees_root."

local_branch_status=0
git_at show-ref --verify --quiet "refs/heads/$branch_name" >/dev/null 2>&1 || local_branch_status=$?
case "$local_branch_status" in
	0)
		die "Local branch already exists: $branch_name"
		;;
	1)
		;;
	*)
		die 'Could not inspect local branch references.'
		;;
esac

registered_worktrees="$(git_at worktree list --porcelain)" || die 'Could not inspect registered worktrees.'
if printf '%s\n' "$registered_worktrees" | awk -v target="$canonical_worktree_path" '$1 == "worktree" && substr($0, 10) == target { found = 1 } END { exit(found ? 0 : 1) }'; then
	die "Worktree path is already registered: $canonical_worktree_path"
fi

remote_branch_status=0
git_at ls-remote --exit-code --refs "$verified_remote" "refs/heads/$branch_name" >/dev/null 2>&1 || remote_branch_status=$?
case "$remote_branch_status" in
	0)
		die "Remote branch already exists on '$verified_remote': $branch_name"
		;;
	2)
		;;
	*)
		die "Could not check for an existing remote branch on '$verified_remote'."
		;;
esac

git_at worktree add -b "$branch_name" "$canonical_worktree_path" refs/heads/main >/dev/null || die 'Could not create the feature branch and worktree.'

say 'PR worktree created.'
say "Remote: $verified_remote ($remote_url)"
say 'Base branch: main'
say "Base commit: $base_commit"
say "Feature branch: $branch_name"
say "Worktree: $canonical_worktree_path"
