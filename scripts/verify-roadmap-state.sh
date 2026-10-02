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
initial_head=$(git_at rev-parse --verify HEAD) || die 'Could not inspect HEAD.'

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
[ "$local_main" = "$initial_head" ] || die 'Main changed during verification; retry with a fresh snapshot.'

baseline_lines=$(grep '^- Review/audit baseline:' "$plan_file" || true)
[ "$(printf '%s\n' "$baseline_lines" | wc -l | tr -d ' ')" = 1 ] || die 'Roadmap must contain exactly one Review/audit baseline.'
baseline=$(printf '%s\n' "$baseline_lines" | sed -nE 's/^- Review\/audit baseline: `([0-9a-f]{40})`.*/\1/p')
[ "${#baseline}" -eq 40 ] || die 'Could not read one 40-character Review/audit baseline from the roadmap.'
[ "$(git_at cat-file -t "$baseline" 2>/dev/null || true)" = commit ] || die 'Roadmap baseline is not an existing commit.'
git_at merge-base --is-ancestor "$baseline" "$local_main" || die 'Roadmap baseline is not an ancestor of current main.'

parent_main=$(git_at rev-parse --verify "$local_main^" 2>/dev/null || true)
audit_relation='current-main'
if [ "$baseline" != "$local_main" ]; then
	# Inspect every intervening commit, including side branches and every merge
	# parent. A product change followed by a revert is NOT bookkeeping.
	commits=$(git_at rev-list "$baseline..$local_main") || die 'Could not enumerate intervening history.'
	bookkeeping_only=yes
	for commit in $commits; do
		changes=$(git_at diff-tree --root -m --no-renames --no-commit-id --raw -r "$commit") || die 'Could not inspect intervening changes.'
		if [ "$plan_path" != docs/ai/MASTER_PLAN.md ] || ! printf '%s\n' "$changes" | awk '
			NF == 0 { next }
			NF != 6 || $6 != "docs/ai/MASTER_PLAN.md" { bad=1 }
			$1 != ":100644" && $1 != ":000000" { bad=1 }
			$2 != "100644" || ($5 != "M" && $5 != "A") { bad=1 }
			END { exit bad ? 1 : 0 }
		'; then
			bookkeeping_only=no
			break
		fi
	done
	if [ "$bookkeeping_only" = no ]; then
		printf 'ROADMAP_STATE=STALE\n' >&2
		printf 'Current main: %s\n' "$local_main" >&2
		printf 'Roadmap baseline: %s\n' "$baseline" >&2
		printf '%s\n' 'Intervening history contains changes outside regular-file roadmap bookkeeping.' >&2
		printf '%s\n' 'Recent first-parent main history:' >&2
		git_at log --first-parent --oneline --decorate -12 "$local_main" >&2
		printf '%s\n' 'ERROR: Reconcile relevant changes before selecting new roadmap work; do not create a plan-only PR merely for a new SHA.' >&2
		exit 1
	fi
	audit_relation='bookkeeping-only-drift'
	if [ -n "$parent_main" ] && [ "$baseline" = "$parent_main" ] && [ "$(printf '%s\n' "$commits" | wc -l | tr -d ' ')" = 1 ]; then
		audit_relation='plan-only-head-parent'
	fi
fi

# READY is a point-in-time planning check, never review/release authority.
[ "$(git_at symbolic-ref --quiet --short HEAD 2>/dev/null || true)" = main ] || die 'Branch changed during verification.'
[ "$(git_at rev-parse --verify HEAD)" = "$initial_head" ] || die 'HEAD changed during verification.'
[ "$(git_at rev-parse --verify "refs/remotes/$remote_name/main")" = "$remote_main" ] || die 'Tracking ref changed during verification.'
final_status=$(git_at status --porcelain --untracked-files=all) || die 'Could not recheck checkout status.'
[ -z "$final_status" ] || die 'Checkout changed during verification.'
printf 'ROADMAP_STATE=READY\n'
printf 'Current main: %s\n' "$local_main"
printf 'Roadmap baseline: %s\n' "$baseline"
printf 'Audit relation: %s\n' "$audit_relation"
printf '%s\n' 'Recent first-parent main history:'
git_at log --first-parent --oneline --decorate -12 "$local_main"
