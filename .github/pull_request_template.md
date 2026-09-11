## What changed

Describe the concrete problem and resulting behavior.

## Validation

- [ ] `sh scripts/validate-release.sh` passes locally.
- [ ] `git diff --check` passes.
- [ ] `CHANGELOG.md` has a user-facing entry under `Unreleased`, or this change has no user-facing effect.
- [ ] Relevant AX4200 behavior was tested, or router testing does not apply.
- [ ] Every affected LuCI page was loaded and exercised in a local browser against
      the lab router, with no error notification, blank view, or new console error;
      or this change cannot affect LuCI.
- [ ] Existing CA material, service state, and PassWall2 routing were preserved unless intentionally changed.
- [ ] No private keys, credentials, router configurations, backups, or generated packages are included.

Include concise commands and results for the checks that apply.
