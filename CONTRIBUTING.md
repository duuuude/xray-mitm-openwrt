# Contributing

This project uses a lightweight branch, test, pull request, and signed release
workflow. Work stays local until the change and its router evidence are ready for
review.

## Start a local branch

Update `main`, then create one branch for one fix or feature. Use `fix/`, `feat/`,
`docs/`, or `chore/` followed by a short description.

**MAC:**

```sh
git switch main
git pull --ff-only
git switch -c fix/short-description
```

**WINDOWS PC (PowerShell):**

```powershell
git switch main
git pull --ff-only
git switch -c fix/short-description
```

Do not commit private keys, CA private material, router configuration, backups,
credentials, or generated APK files.

## Develop and validate

Add a short user-facing entry under `Unreleased` in `CHANGELOG.md`. Run the full
offline validation before router testing.

**MAC:**

```sh
sh scripts/validate-release.sh
```

**WINDOWS PC (PowerShell with WSL):**

```powershell
wsl.exe sh -lc 'cd /path/to/xray-mitm-openwrt && sh scripts/validate-release.sh'
```

Review the complete diff and commit only the intended files:

```sh
git diff --check
git diff
git status --short
```

## Test on the AX4200

For changes that affect packages, services, certificates, LuCI, installation, or
PassWall2, build the APKs and test them on the lab router. Preserve the active CA,
service state, and routing unless the change explicitly targets them.

Every LuCI JavaScript, template, style, RPC-response, or ACL change must also pass
a real local-browser test against the lab router before it is pushed:

1. Install or stage the exact candidate files on the router.
2. Open the affected LuCI page from a local desktop browser and reload it directly
   so cached JavaScript is not reused.
3. Confirm the complete page renders without an error notification or blank view.
4. Exercise every affected control and state transition, including preview/apply
   behavior when routing code changed.
5. Inspect the browser console after the reload and interactions; there must be no
   new JavaScript errors.
6. Record the tested commit, router package or staged-file version, page, controls,
   and result in the pull request.

Static validation and GitHub Actions do not replace this browser test. Do not push,
merge, tag, or publish a LuCI change when the real page has not passed it.

After the browser test passes, show the exact tested UI candidate to the project
owner and obtain explicit visual approval. Do not push, merge, tag, or publish a
UI-affecting change until that approval is recorded; passing tests or silence do
not count as approval.

Verify the affected behavior, update from the prior signed version, rollback when
relevant, and reboot when startup persistence is in scope. Follow
`docs/RELEASE_TESTING.md` for a public release.

## Open and merge a pull request

Push only after local checks and applicable router tests pass. Complete the pull
request checklist with concrete results. Merge after GitHub Actions passes and the
diff has been reviewed.

Small fixes may accumulate on `main`. Create a public version when users need the
change: increment the patch version for compatible fixes and the minor version for
new compatible behavior.

## Publish a signed release

Move the relevant `Unreleased` entries into a dated version section, update
`PKG_VERSION`, set `PKG_RELEASE:=1`, and run the release validation. The signed tag
must be exactly `v${PKG_VERSION}`. The protected workflow extracts that version's
notes from `CHANGELOG.md`, builds the packages, signs the APK feed, and publishes the
GitHub Release.

The release sequence is:

```text
local branch -> offline checks -> AX4200 test -> PR and CI -> merge -> signed tag -> authenticated update test
```

Never put the APK signing private key in the repository, release assets, workflow
artifacts, terminal transcripts, or router files.
