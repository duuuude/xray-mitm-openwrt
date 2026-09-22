#!/bin/sh
set -eu

usage() {
	printf '%s\n' 'Usage: scripts/verify-roadmap-state.sh [remote] [plan-path]' >&2
	exit 2
}

die() {
	printf 'ROADMAP_STATE=BLOCKED\nERROR: %s\n' "$*" >&2
	exit 1
}

[ "$#" -le 2 ] || usage

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
project_dir=$(CDPATH= cd -- "$script_dir/.." && pwd -P)
remote_name=${1:-origin}
plan_path=${2:-docs/ai/MASTER_PLAN.md}
remote_verifier="$script_dir/verify-github-remote.sh"

git_at() {
	git -C "$project_dir" "$@"
}

resolve_plan_path() (
	path=$1

	case "$path" in
		''|/*) exit 1 ;;
	esac
	case "/$path/" in
		*/../*|*/./*) exit 1 ;;
	esac

	path="$project_dir/$path"
	symlink_count=0
	while [ -L "$path" ]; do
		[ "$symlink_count" -lt 40 ] || exit 1
		parent=$(CDPATH= cd -- "$(dirname -- "$path")" && pwd -P) || exit 1
		name=$(basename -- "$path") || exit 1
		target=$(readlink "$parent/$name") || exit 1
		case "$target" in
			/*) path=$target ;;
			*) path="$parent/$target" ;;
		esac
		symlink_count=$((symlink_count + 1))
	done

	parent=$(CDPATH= cd -- "$(dirname -- "$path")" && pwd -P) || exit 1
	resolved="$parent/$(basename -- "$path")"
	[ -f "$resolved" ] || exit 1
	case "$resolved" in
		"$project_dir"/*) printf '%s\n' "$resolved" ;;
		*) exit 1 ;;
	esac
)

[ -d "$project_dir" ] || die "Project directory does not exist: $project_dir"
git_root=$(git_at rev-parse --show-toplevel 2>/dev/null) || die 'Could not inspect the Git repository root.'
[ "$git_root" = "$project_dir" ] || die 'The helper must run from the canonical repository checkout.'

current_branch=$(git_at symbolic-ref --quiet --short HEAD 2>/dev/null || true)
[ "$current_branch" = main ] || die "The canonical checkout must be on main; current branch is ${current_branch:-detached HEAD}."

status_output=$(git_at status --porcelain --untracked-files=all 2>/dev/null) || die 'Could not inspect the canonical main status.'
[ -z "$status_output" ] || die 'The canonical main checkout is not clean.'

plan_file=$(resolve_plan_path "$plan_path") || die 'The roadmap path must resolve to an existing repository-relative file within the repository.'
plan_path=${plan_file#"$project_dir"/}
[ -f "$remote_verifier" ] || die 'Required scripts/verify-github-remote.sh is missing.'
sh "$remote_verifier" "$remote_name" || die 'The configured remote does not resolve to the verified GitHub repository.'

if ! git_at fetch --quiet --no-tags "$remote_name" "refs/heads/main:refs/remotes/$remote_name/main"; then
	die "Could not refresh main from verified GitHub remote '$remote_name'."
fi

local_main=$(git_at rev-parse --verify refs/heads/main 2>/dev/null) || die 'The local main branch does not exist.'
remote_main=$(git_at rev-parse --verify "refs/remotes/$remote_name/main" 2>/dev/null) || die "The fetched $remote_name/main ref does not exist; refresh the verified remote first."
[ "$local_main" = "$remote_main" ] || die "Local main $local_main does not match fetched $remote_name/main $remote_main."

baseline_line=$(grep -E '^- Review/audit baseline: `[0-9a-f]{40}`' "$plan_file" | sed -n '1p' || true)
baseline=$(printf '%s\n' "$baseline_line" | sed -E 's/.*`([0-9a-f]{40})`.*/\1/' || true)
[ "${#baseline}" -eq 40 ] || die 'Could not read one 40-character Review/audit baseline from the roadmap.'

parent_main=$(git_at rev-parse --verify "$local_main^" 2>/dev/null || true)
changed_at_head=$(git_at diff-tree --no-commit-id --name-only -r "$local_main" | sed '/^$/d')

audit_relation='current-main'
if [ "$baseline" != "$local_main" ]; then
	if [ -n "$parent_main" ] && [ "$baseline" = "$parent_main" ] && [ "$changed_at_head" = "$plan_path" ]; then
		audit_relation='plan-only-head-parent'
	else
		printf 'ROADMAP_STATE=STALE\n' >&2
		printf 'Current main: %s\n' "$local_main" >&2
		printf 'Roadmap baseline: %s\n' "$baseline" >&2
		printf 'Expected baseline: %s or a plan-only HEAD parent\n' "$local_main" >&2
		printf '%s\n' 'Recent first-parent main history:' >&2
		git_at log --first-parent --oneline --decorate -12 "$local_main" >&2
		printf '%s\n' 'ERROR: Refresh and reconcile MASTER_PLAN.md against current main before selecting the next item.' >&2
		exit 1
	fi
fi

printf 'ROADMAP_STATE=READY\n'
printf 'Current main: %s\n' "$local_main"
printf 'Roadmap baseline: %s\n' "$baseline"
printf 'Audit relation: %s\n' "$audit_relation"
printf '%s\n' 'Recent first-parent main history:'
git_at log --first-parent --oneline --decorate -12 "$local_main"
