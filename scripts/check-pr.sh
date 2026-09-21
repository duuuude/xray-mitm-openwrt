#!/bin/sh
set -eu

usage() {
	printf '%s\n' 'Usage: scripts/check-pr.sh [base-ref] [candidate-ref]' >&2
	exit 2
}

die() {
	printf 'CHECK_PR_RESULT=BLOCKED\nERROR: %s\n' "$*" >&2
	exit 1
}

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
project_dir=$(CDPATH= cd -- "$script_dir/.." && pwd -P)

[ "$#" -le 2 ] || usage

base_input=${1:-origin/main}
candidate_input=${2:-HEAD}

git_at() {
	git -C "$project_dir" "$@"
}

is_sha() {
	value=$1
	[ "${#value}" -eq 40 ] || return 1
	case "$value" in
		*[!0123456789abcdef]*) return 1 ;;
		*) return 0 ;;
	esac
}

[ -d "$project_dir" ] || die "Project directory does not exist: $project_dir"
git_root=$(git_at rev-parse --show-toplevel 2>/dev/null) || die 'Could not inspect the Git repository root.'
[ "$git_root" = "$project_dir" ] || die 'The check must run from the repository checkout containing this script.'

status_output=$(git_at status --porcelain --untracked-files=all 2>/dev/null) || die 'Could not inspect the working-tree status.'
[ -z "$status_output" ] || die 'The candidate checkout is not clean; refusing to produce commit-bound evidence.'

current_head=$(git_at rev-parse --verify HEAD 2>/dev/null) || die 'Could not resolve the current checkout HEAD.'
is_sha "$current_head" || die 'The current checkout HEAD is not a full commit SHA.'

case "$base_input" in
	''|-*) die 'The base ref must not be empty or begin with a dash.' ;;
esac
case "$candidate_input" in
	''|-*) die 'The candidate ref must not be empty or begin with a dash.' ;;
esac

base_sha=$(git_at rev-parse --verify "$base_input^{commit}" 2>/dev/null) || die "Could not resolve base ref: $base_input"
candidate_sha=$(git_at rev-parse --verify "$candidate_input^{commit}" 2>/dev/null) || die "Could not resolve candidate ref: $candidate_input"
is_sha "$base_sha" || die 'The resolved base is not a full commit SHA.'
is_sha "$candidate_sha" || die 'The resolved candidate is not a full commit SHA.'
[ "$candidate_sha" = "$current_head" ] || die "Candidate ref resolves to $candidate_sha, but the checkout HEAD is $current_head."

ancestor_status=0
git_at merge-base --is-ancestor "$base_sha" "$candidate_sha" >/dev/null 2>&1 || ancestor_status=$?
case "$ancestor_status" in
	0) ;;
	1) die "Base commit $base_sha is not an ancestor of candidate $candidate_sha." ;;
	*) die 'Could not verify base/candidate ancestry.' ;;
esac

changed_files=$(git_at diff --name-only --no-renames "$base_sha" "$candidate_sha" 2>/dev/null) || die 'Could not inspect the exact base/candidate diff.'
[ -n "$changed_files" ] || die 'The exact base/candidate diff contains no changed files.'

docs=0
shell=0
python=0
frontend=0
passwall2=0
installer=0
package=0
release=0
workflow_security=0
unknown=0
focus_certificates=0
focus_config=0
focus_ctl=0
focus_frontend=0
focus_installer=0
focus_passwall2=0
focus_promotion_artifact=0
focus_release_preflight=0
focus_signed_feed=0
focus_start_pr=0
focus_startup=0
focus_check_pr=0

classify_path() {
	path=$1
	known=0

	case "$path" in
		docs/*|*.md|*.markdown|*.txt)
			docs=1
			known=1
			;;
	esac
	case "$path" in
		*.sh|xray-mitm/files/etc/init.d/*|xray-mitm/files/usr/libexec/*|xray-mitm/files/usr/sbin/*)
			shell=1
			known=1
			;;
	esac
	case "$path" in
		*.py)
			python=1
			known=1
			;;
	esac
	case "$path" in
		*.js|*.uc|luci-app-xray-mitm/htdocs/*|luci-app-xray-mitm/root/usr/share/luci/*|luci-app-xray-mitm/root/usr/share/rpcd/*)
			frontend=1
			focus_frontend=1
			known=1
			;;
	esac
	case "$path" in
		*passwall2*|*PassWall2*)
			passwall2=1
			focus_passwall2=1
			known=1
			;;
	esac
	case "$path" in
		install.sh|*installer*|tests/test_installer.py)
			installer=1
			focus_installer=1
			known=1
			;;
	esac
	case "$path" in
		xray-mitm/*|luci-app-xray-mitm/*|*/Makefile|Makefile)
			package=1
			known=1
			;;
	esac
	case "$path" in
		scripts/release-*|scripts/check-release-version.sh|scripts/release-notes.sh|scripts/sign-apk-index.sh|scripts/verify-promotion-artifact.sh|.github/workflows/build.yml|.github/workflows/publish-feed.yml|keys/*)
			release=1
			known=1
			;;
	esac
	case "$path" in
		.github/*|keys/*|SECURITY.md)
			workflow_security=1
			known=1
			;;
	esac

	case "$path" in
		tests/test_certificates.py) focus_certificates=1 ;;
		tests/test_config.py) focus_config=1 ;;
		tests/test_ctl.py) focus_ctl=1 ;;
		tests/test_installer.py) focus_installer=1 ;;
		tests/test_passwall2.py) focus_passwall2=1 ;;
		tests/test_promotion_artifact.py) focus_promotion_artifact=1 ;;
		tests/test_release_preflight.py) focus_release_preflight=1 ;;
		tests/test_signed_feed.py) focus_signed_feed=1 ;;
		tests/test_start_pr.py) focus_start_pr=1 ;;
		tests/test_startup.py) focus_startup=1 ;;
		tests/test_check_pr.py) focus_check_pr=1 ;;
	esac
	case "$path" in
		scripts/release-preflight.sh) focus_release_preflight=1 ;;
		scripts/sign-apk-index.sh|scripts/verify-promotion-artifact.sh|.github/workflows/build.yml) focus_promotion_artifact=1 ;;
		scripts/start-pr.sh) focus_start_pr=1 ;;
		.github/workflows/sign-candidate.yml|docs/SIGNED_FEED.md) focus_signed_feed=1 ;;
	esac

	[ "$known" -eq 1 ] || unknown=1
}

while IFS= read -r changed_path; do
	[ -n "$changed_path" ] || continue
	classify_path "$changed_path"
done <<EOF
$changed_files
EOF

categories=''
add_category() {
	if [ -z "$categories" ]; then
		categories=$1
	else
		categories="$categories,$1"
	fi
}

[ "$docs" -eq 1 ] && add_category documentation
[ "$shell" -eq 1 ] && add_category shell
[ "$python" -eq 1 ] && add_category python
[ "$frontend" -eq 1 ] && add_category frontend
[ "$package" -eq 1 ] && add_category package
[ "$passwall2" -eq 1 ] && add_category passwall2
[ "$installer" -eq 1 ] && add_category installer
[ "$release" -eq 1 ] && add_category release
[ "$workflow_security" -eq 1 ] && add_category workflow-security
[ "$unknown" -eq 1 ] && add_category unknown

printf '%s\n' 'CHECK_PR_FORMAT_VERSION=1'
printf 'Base input: %s\n' "$base_input"
printf 'Base commit: %s\n' "$base_sha"
printf 'Candidate input: %s\n' "$candidate_input"
printf 'Candidate commit: %s\n' "$candidate_sha"
printf 'Changed file count: %s\n' "$(printf '%s\n' "$changed_files" | awk 'NF { count += 1 } END { print count + 0 }')"
printf 'Changed files:\n%s\n' "$changed_files"
printf 'Categories: %s\n' "$categories"

[ "$unknown" -eq 0 ] || die 'At least one changed path has no validation mapping.'

temporary_dir=$(mktemp -d "${TMPDIR:-/tmp}/xray-mitm-check-pr.XXXXXX") || die 'Could not create a temporary evidence directory.'
cleanup() {
	rm -rf "$temporary_dir"
}
trap cleanup EXIT HUP INT TERM

safe_home="$temporary_dir/home"
safe_git_config="$temporary_dir/gitconfig"
mkdir -p "$safe_home"
: >"$safe_git_config"
safe_path=${PATH:-/usr/bin:/bin}
safe_node_bin=${NODE_BIN:-}

test_failures=0
manual_blocked=0
log_number=0
last_log=''

run_check() {
	label=$1
	display_command=$2
	shift 2
	log_number=$((log_number + 1))
	last_log="$temporary_dir/$log_number.log"
	printf '%s\n' "$label"
	printf 'Command: %s\n' "$display_command"
	if [ -n "$safe_node_bin" ]; then
		if env -i \
			"PATH=$safe_path" \
			"HOME=$safe_home" \
			"TMPDIR=$temporary_dir" \
			"LC_ALL=C" \
			"NODE_BIN=$safe_node_bin" \
			"GIT_CONFIG_GLOBAL=$safe_git_config" \
			GIT_CONFIG_NOSYSTEM=1 \
			GIT_TERMINAL_PROMPT=0 \
			"$@" >"$last_log" 2>&1; then
			printf '%s\n' 'Result: PASS'
		else
			run_status=$?
			printf 'Result: FAIL (exit %s; command output suppressed)\n' "$run_status"
			test_failures=1
		fi
	elif env -i \
		"PATH=$safe_path" \
		"HOME=$safe_home" \
		"TMPDIR=$temporary_dir" \
		"LC_ALL=C" \
		"GIT_CONFIG_GLOBAL=$safe_git_config" \
		GIT_CONFIG_NOSYSTEM=1 \
		GIT_TERMINAL_PROMPT=0 \
		"$@" >"$last_log" 2>&1; then
		printf '%s\n' 'Result: PASS'
	else
		run_status=$?
		printf 'Result: FAIL (exit %s; command output suppressed)\n' "$run_status"
		test_failures=1
	fi
}

run_shell_syntax_for_changed_files() {
	while IFS= read -r changed_path; do
		case "$changed_path" in
			*.sh|xray-mitm/files/etc/init.d/*|xray-mitm/files/usr/libexec/*|xray-mitm/files/usr/sbin/*)
				if [ -f "$project_dir/$changed_path" ]; then
					run_check "Focused shell syntax: $changed_path" "sh -n $changed_path" sh -n "$project_dir/$changed_path"
				else
					printf 'Focused shell syntax: %s\nResult: SKIPPED (file is deleted in candidate)\n' "$changed_path"
					manual_blocked=1
				fi
				;;
		esac
	done <<EOF
$changed_files
EOF
}

run_node_checks_for_changed_files() {
	node_bin=${NODE_BIN:-}
	if [ -n "$node_bin" ]; then
		if [ -x "$node_bin" ]; then
			:
		elif command -v "$node_bin" >/dev/null 2>&1; then
			node_bin=$(command -v "$node_bin")
		else
			node_bin=''
		fi
	else
		node_bin=$(command -v node 2>/dev/null || true)
	fi

	if [ -z "$node_bin" ]; then
		printf '%s\n' 'Focused frontend checks: SKIPPED (Node.js is unavailable; set NODE_BIN to an executable).'
		manual_blocked=1
		return
	fi

	while IFS= read -r changed_path; do
		case "$changed_path" in
			*.js)
				if [ -f "$project_dir/$changed_path" ]; then
					run_check "Focused JavaScript syntax: $changed_path" "${node_bin} --check $changed_path" "$node_bin" --check "$project_dir/$changed_path"
				else
					printf 'Focused JavaScript syntax: %s\nResult: SKIPPED (file is deleted in candidate)\n' "$changed_path"
					manual_blocked=1
				fi
				;;
		esac
	done <<EOF
$changed_files
EOF
	run_check 'Focused frontend-state tests' "${node_bin} tests/test_frontend_state.js" "$node_bin" "$project_dir/tests/test_frontend_state.js"
}

if [ "$shell" -eq 1 ]; then
	run_shell_syntax_for_changed_files
fi

if [ "$frontend" -eq 1 ]; then
	run_node_checks_for_changed_files
fi

if [ "$focus_certificates" -eq 1 ]; then
	run_check 'Focused certificate tests' 'PYTHONDONTWRITEBYTECODE=1 python3 tests/test_certificates.py' env PYTHONDONTWRITEBYTECODE=1 python3 "$project_dir/tests/test_certificates.py"
fi
if [ "$focus_config" -eq 1 ]; then
	run_check 'Focused configuration tests' 'PYTHONDONTWRITEBYTECODE=1 python3 tests/test_config.py' env PYTHONDONTWRITEBYTECODE=1 python3 "$project_dir/tests/test_config.py"
fi
if [ "$focus_ctl" -eq 1 ]; then
	run_check 'Focused control tests' 'PYTHONDONTWRITEBYTECODE=1 python3 tests/test_ctl.py' env PYTHONDONTWRITEBYTECODE=1 python3 "$project_dir/tests/test_ctl.py"
fi
if [ "$focus_installer" -eq 1 ]; then
	run_check 'Focused installer tests' 'PYTHONDONTWRITEBYTECODE=1 python3 tests/test_installer.py' env PYTHONDONTWRITEBYTECODE=1 python3 "$project_dir/tests/test_installer.py"
fi
if [ "$focus_passwall2" -eq 1 ]; then
	run_check 'Focused PassWall2 tests' 'PYTHONDONTWRITEBYTECODE=1 python3 tests/test_passwall2.py' env PYTHONDONTWRITEBYTECODE=1 python3 "$project_dir/tests/test_passwall2.py"
fi
if [ "$focus_promotion_artifact" -eq 1 ]; then
	run_check 'Focused promotion-artifact tests' 'PYTHONDONTWRITEBYTECODE=1 python3 tests/test_promotion_artifact.py' env PYTHONDONTWRITEBYTECODE=1 python3 "$project_dir/tests/test_promotion_artifact.py"
fi
if [ "$focus_release_preflight" -eq 1 ]; then
	run_check 'Focused release-preflight tests' 'PYTHONDONTWRITEBYTECODE=1 python3 tests/test_release_preflight.py' env PYTHONDONTWRITEBYTECODE=1 python3 "$project_dir/tests/test_release_preflight.py"
fi
if [ "$focus_signed_feed" -eq 1 ]; then
	run_check 'Focused signed-feed tests' 'PYTHONDONTWRITEBYTECODE=1 python3 tests/test_signed_feed.py' env PYTHONDONTWRITEBYTECODE=1 python3 "$project_dir/tests/test_signed_feed.py"
fi
if [ "$focus_start_pr" -eq 1 ]; then
	run_check 'Focused start-pr tests' 'PYTHONDONTWRITEBYTECODE=1 python3 tests/test_start_pr.py' env PYTHONDONTWRITEBYTECODE=1 python3 "$project_dir/tests/test_start_pr.py"
fi
if [ "$focus_startup" -eq 1 ]; then
	run_check 'Focused startup tests' 'PYTHONDONTWRITEBYTECODE=1 python3 tests/test_startup.py' env PYTHONDONTWRITEBYTECODE=1 python3 "$project_dir/tests/test_startup.py"
fi
if [ "$focus_check_pr" -eq 1 ]; then
	run_check 'Focused check-pr tests' 'PYTHONDONTWRITEBYTECODE=1 python3 tests/test_check_pr.py' env PYTHONDONTWRITEBYTECODE=1 python3 "$project_dir/tests/test_check_pr.py"
fi

run_check 'Exact base/candidate whitespace check' "git diff --check $base_sha $candidate_sha" git -C "$project_dir" diff --check "$base_sha" "$candidate_sha"

run_check 'Full repository validation' 'sh scripts/validate-release.sh' sh "$project_dir/scripts/validate-release.sh"
full_validation_log=$last_log
if grep -q 'LuCI JavaScript syntax check skipped' "$full_validation_log"; then
	printf '%s\n' 'Skipped check: full validator could not run LuCI JavaScript checks because Node.js was unavailable.'
	if [ "$frontend" -eq 1 ]; then
		manual_blocked=1
	fi
fi

post_status=''
if post_status=$(git_at status --porcelain --untracked-files=all 2>/dev/null); then
	if [ -n "$post_status" ]; then
		printf '%s\n' 'Post-validation working-tree check: FAIL (changes detected; details suppressed)'
		test_failures=1
	else
		printf '%s\n' 'Post-validation working-tree check: PASS'
	fi
else
	printf '%s\n' 'Post-validation working-tree check: FAIL (Git status could not be inspected)'
	test_failures=1
fi

post_head=''
if post_head=$(git_at rev-parse --verify HEAD 2>/dev/null); then
	if [ "$post_head" = "$candidate_sha" ]; then
		printf '%s\n' 'Post-validation HEAD check: PASS'
	else
		printf 'Post-validation HEAD check: FAIL (expected candidate %s)\n' "$candidate_sha"
		test_failures=1
	fi
else
	printf '%s\n' 'Post-validation HEAD check: FAIL (HEAD could not be inspected)'
	test_failures=1
fi

printf '%s\n' 'Manual gates:'
if [ "$frontend" -eq 1 ]; then
	printf '%s\n' 'OpenWrt integration: REQUIRED (not performed by this read-only check)'
	printf '%s\n' 'AX4200/browser validation: REQUIRED (not performed by this read-only check)'
	manual_blocked=1
elif [ "$passwall2" -eq 1 ] || [ "$package" -eq 1 ] || [ "$installer" -eq 1 ]; then
	printf '%s\n' 'OpenWrt integration: REQUIRED (not performed by this read-only check)'
	printf '%s\n' 'AX4200/browser validation: not required by the changed categories'
	manual_blocked=1
else
	printf '%s\n' 'OpenWrt integration: not required'
	printf '%s\n' 'AX4200/browser validation: not required'
fi
if [ "$release" -eq 1 ]; then
	printf '%s\n' 'Release execution: owner-gated and not performed by this check'
else
	printf '%s\n' 'Release execution: not required'
fi
if [ "$workflow_security" -eq 1 ]; then
	printf '%s\n' 'Signing/security execution: review-only; no secrets or signing operation used'
else
	printf '%s\n' 'Signing/security execution: not required'
fi

printf '%s\n' 'Evidence boundary:'
printf '%s\n' '- Offline tests and static checks do not prove live router, browser, external-service, release, or signing behavior.'
if [ "$docs" -eq 1 ]; then
	printf '%s\n' '- Markdown rendering/link validation: SKIPPED (no dedicated repository validator).'
fi
if [ "$frontend" -eq 1 ]; then
	printf '%s\n' '- LuCI rendering, browser console behavior, and saved router-state preservation: UNPROVEN until the required manual gate is completed.'
fi
if [ "$passwall2" -eq 1 ]; then
	printf '%s\n' '- Live PassWall2 routing and rollback behavior: UNPROVEN until the required AX4200 gate is completed.'
fi

if [ "$test_failures" -ne 0 ]; then
	printf '%s\n' 'CHECK_PR_RESULT=FAILED'
	exit 1
fi
if [ "$manual_blocked" -ne 0 ]; then
	printf '%s\n' 'CHECK_PR_RESULT=BLOCKED'
	exit 1
fi
printf '%s\n' 'CHECK_PR_RESULT=READY_FOR_REVIEW'
