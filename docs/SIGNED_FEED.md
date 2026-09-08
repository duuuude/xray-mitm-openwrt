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
5. The tag-only workflow receives the signing key only after the `signed-feed` environment gate.

Never put the private feed key in the repository, a pull-request secret, workflow artifact, release, router image, or command transcript.

## One-time GitHub configuration

1. Create the `signed-feed` environment under **Settings → Environments**.
2. Add required reviewers and prevent unreviewed deployment where supported.
3. Add the complete private PEM as the environment secret `XRAY_MITM_APK_PRIVATE_KEY`.
4. Set **Settings → Pages → Source** to **GitHub Actions**.
5. Protect `main` and require the normal build checks.

The workflow derives a public key from the secret and compares it with the committed public key before building. It never prints private-key material.

## Publish a release

1. Set `PKG_VERSION` in `xray-mitm/Makefile` and reset `PKG_RELEASE` to `1`.
2. Update the LuCI version only when the LuCI package changed.
3. Run `sh scripts/validate-release.sh`.
4. Merge the reviewed change to `main` and wait for its build.
5. Create and push a signed tag exactly matching `v${PKG_VERSION}`.
6. Review and approve the `signed-feed` environment job.
7. Confirm Pages and the GitHub Release contain both APKs, `packages.adb`, checksums, source commit, public key, and fingerprint.
8. Complete [RELEASE_TESTING.md](RELEASE_TESTING.md).

**MAC:**

```sh
git switch main
git pull --ff-only
sh scripts/validate-release.sh
git tag -s v0.2.0 -m 'xray-mitm v0.2.0'
git tag -v v0.2.0
git push origin v0.2.0
```

**WINDOWS PC (PowerShell with Git and a configured signing key):**

```powershell
git switch main
git pull --ff-only
wsl.exe sh -lc 'cd /path/to/xray-mitm-openwrt && sh scripts/validate-release.sh'
git tag -s v0.2.0 -m "xray-mitm v0.2.0"
git tag -v v0.2.0
git push origin v0.2.0
```

Replace `v0.2.0` with the reviewed version. The workflow rejects a mismatched tag or package release other than `r1`.

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
apk add xray-mitm luci-app-xray-mitm
```

For rollback, download both APKs from one older signed release, verify its checksums, and install both together. Test configuration compatibility before crossing a schema change. Never use unrestricted `apk upgrade` as the project updater.

Rotate keys while the old key remains trusted: generate a new offline key, commit only its public half and fingerprint, update the installer to add it beside the old key, publish a transition release signed by the old key, migrate existing routers, then switch signing. Remove the old public key only after the migration window.

If compromise is suspected, stop publishing, disable the environment secret, publish a security notice, and require verification of a replacement fingerprint through an independent channel. Never silently replace the public key at the same URL.
