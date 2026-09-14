# Signed APK feed operations

This runbook is for maintainers. New users should follow [README.md](../README.md) or [README.fa.md](../README.fa.md).

## Trust boundary

The public bootstrap pins this P-256 feed key:

```text
File: keys/xray-mitm-feed-v1.pem
SHA-256: 3e0dc07ffef69d1512500b6add486381d8c261a8ec3fcce54fa403b35320df8a
```

Keep the matching private key outside the repository. Retain one encrypted offline backup and store the automation copy only as `XRAY_MITM_APK_PRIVATE_KEY` in the protected GitHub environment named `signed-feed`.

The trust chain is:

1. GitHub HTTPS delivers the bootstrap installer.
2. The installer accepts only the public key with the hard-coded fingerprint.
3. APK stores that key in `/etc/apk/keys/xray-mitm-feed-v1.pem`.
4. APK verifies the signed `packages.adb` index and packages on every install or update.
5. The tag-only publishing workflow receives the signing key only after the `signed-feed` environment gate. The separate protected candidate workflow uses that same gate for an owner-approved lab artifact and does not publish it.

Never put the private feed key in the repository, a pull-request secret, workflow artifact, release, router image, or command transcript.

## One-time GitHub configuration

1. Create the `signed-feed` environment under **Settings → Environments**.
2. Add required reviewers and prevent unreviewed deployment where supported.
3. Add the complete private PEM as the environment secret `XRAY_MITM_APK_PRIVATE_KEY`.
4. Set **Settings → Pages → Source** to **GitHub Actions**.
5. Protect `main` and require the normal build checks.

The workflow derives a public key from the secret and compares it with the committed public key before building. It never prints private-key material.

## Protected PR candidate validation

The `Sign protected PR candidate APKs` workflow is a manual, non-publishing path for validating one exact pull-request head on a real test router. It is intentionally fixed to the supported OpenWrt `25.12.5` and `aarch64_generic` build target.

Dispatch it from `main` only after the owner has approved the candidate and the router-validation scope. Supply the open PR number and its exact 40-character head SHA. Before the protected job receives the signing secret, the workflow verifies that the PR is open, targets `main`, belongs to this repository, and still points to that exact head. It then checks out and validates that commit.

After the `signed-feed` environment gate is approved, the workflow builds the two APKs and signed `packages.adb`, then uploads a seven-day audit artifact containing the package files, checksums, source and base commits, PR number, and public key fingerprint. The artifact is for controlled lab validation only. This workflow creates no tag, GitHub Release, Pages deployment, or release feed publication.

The private key remains only in the protected environment and the short-lived runner workspace. Never copy it into the repository, pull-request data, artifact, router, or command transcript. If the candidate head changes, dispatch a new run for the new exact SHA rather than reusing an older artifact.

## Publish a release

1. Move the release entries from `Unreleased` into a dated version section in `CHANGELOG.md`.
2. Set `PKG_VERSION` in `xray-mitm/Makefile` and reset `PKG_RELEASE` to `1`.
3. Update the LuCI version only when the LuCI package changed.
4. Run `sh scripts/validate-release.sh`.
5. Merge the reviewed change to `main` and wait for its build.
6. Run `sh scripts/release-preflight.sh` from the clean, synchronized `main` branch.
7. Create and push a signed tag exactly matching `v${PKG_VERSION}`.
8. Review and approve the `signed-feed` environment job.
9. Confirm Pages and the GitHub Release contain both APKs, `packages.adb`, checksums, source commit, public key, and fingerprint. Confirm the GitHub Release notes match the version section in `CHANGELOG.md`.
10. Complete [RELEASE_TESTING.md](RELEASE_TESTING.md).

**MAC:**

```sh
git switch main
git pull --ff-only
sh scripts/validate-release.sh
git tag -s v0.2.2 -m 'xray-mitm v0.2.2'
git tag -v v0.2.2
git push origin v0.2.2
```

**WINDOWS PC (PowerShell with Git and a configured signing key):**

```powershell
git switch main
git pull --ff-only
wsl.exe sh -lc 'cd /path/to/xray-mitm-openwrt && sh scripts/validate-release.sh'
git tag -s v0.2.2 -m "xray-mitm v0.2.2"
git tag -v v0.2.2
git push origin v0.2.2
```

Replace `v0.2.2` with the reviewed version. The workflow rejects a mismatched tag,
a package release other than `r1`, or a version without changelog notes.

## Verify the published key

**MAC:**

```sh
curl -fsSLO https://duuuude.github.io/xray-mitm-openwrt/feed/xray-mitm-feed-v1.pem
printf '%s  %s\n' \
  '3e0dc07ffef69d1512500b6add486381d8c261a8ec3fcce54fa403b35320df8a' \
  'xray-mitm-feed-v1.pem' | shasum -a 256 -c -
```

**WINDOWS PC (PowerShell):**

```powershell
Invoke-WebRequest `
  -Uri 'https://duuuude.github.io/xray-mitm-openwrt/feed/xray-mitm-feed-v1.pem' `
  -OutFile '.\xray-mitm-feed-v1.pem'
(Get-FileHash '.\xray-mitm-feed-v1.pem' -Algorithm SHA256).Hash.ToLowerInvariant()
```

The Windows result must match the fingerprint above. A successful `apk update` on a clean test router is the native signature check for the configured feed.

## Update, rollback, and key rotation

The live feed contains the current supported version. Every signed version is also kept as GitHub Release assets. Routine updates use:

**ROUTER:**

```sh
apk update
apk upgrade xray-mitm luci-app-xray-mitm
```

For rollback, download both APKs from one older signed release, verify its checksums, and install both together. Test configuration compatibility before crossing a schema change. Never use unrestricted `apk upgrade` as the project updater.

Rotate keys while the old key remains trusted: generate a new offline key, commit only its public half and fingerprint, update the installer to add it beside the old key, publish a transition release signed by the old key, migrate existing routers, then switch signing. Remove the old public key only after the migration window.

If compromise is suspected, stop publishing, disable the environment secret, publish a security notice, and require verification of a replacement fingerprint through an independent channel. Never silently replace the public key at the same URL.
