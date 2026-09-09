# Release testing

Every public version passes offline validation, a protected signed build, and router testing.

## 1. Offline checks

The validator checks package layout, JSON, localhost listeners, certificate paths, disabled first-run state, dependencies, ACLs, noarch declarations, pinned Actions, feed-key fingerprint, installer rollback, and secret exclusions. It also runs certificate, PassWall2, startup, shell, and LuCI JavaScript tests.

**MAC:**

```sh
cd "/path/to/xray-mitm-openwrt"
sh scripts/validate-release.sh
```

**WINDOWS PC (PowerShell with WSL):**

```powershell
wsl.exe sh -lc 'cd /path/to/xray-mitm-openwrt && sh scripts/validate-release.sh'
```

These checks are offline and do not connect to a router.

## 2. Signed publishing checks

Before the tag:

1. Confirm `CHANGELOG.md` has a dated section for the intended version and no released entries remain under `Unreleased`.
2. Confirm `PKG_VERSION` is intended, `PKG_RELEASE` is `1`, and the tag will be exactly `v${PKG_VERSION}`.
3. Review the full diff and confirm only `keys/xray-mitm-feed-v1.pem` is public-key material.
4. Confirm the private key exists only in protected storage and the `signed-feed` environment secret.
5. Confirm required environment reviewers and GitHub Pages are configured.

After approving the tagged workflow:

1. Confirm the protected job proves the private/public key match.
2. Confirm exactly one core APK, one LuCI APK, and one `packages.adb` are produced.
3. Confirm the GitHub Release also contains `SHA256SUMS`, `SOURCE_COMMIT`, `PUBLIC_KEY_SHA256`, and the public key.
4. Confirm Pages serves the key and `feed/25.12/all/packages.adb` over HTTPS.
5. Independently verify key SHA-256 `3e0dc07ffef69d1512500b6add486381d8c261a8ec3fcce54fa403b35320df8a`.

## 3. Clean-router installation

Use a disposable or lab router:

1. Confirm official OpenWrt 25.12.5 or a later 25.12 maintenance release and APK.
2. Run the public one-command installer.
3. Confirm the expected fingerprint and that `--allow-untrusted` is absent.
4. Confirm the project key and repository list exist under `/etc/apk/`.
5. Confirm the service remains stopped, UCI `enabled` and `boot_enabled` are zero, and no xray-mitm boot link exists.
6. Confirm PassWall2, firewall, DNS, and routing are unchanged.
7. Generate and activate a CA; confirm its private key is `root` owned with mode `0600`.
8. Download only the public certificate, start the service, and pass the health check.
9. Confirm all listeners bind only to `127.0.0.1`.
10. Preview PassWall2 changes, compare with a fresh backup, apply, verify routes, and exercise exact rollback.
11. Confirm a MITM domain shows `CN=MITM-DomainFronting` while a control domain shows its public issuer.
12. Reboot and repeat service, routing, health, and client checks.

## 4. Existing-router update

1. Start with a working prior version, active CA, boot setting, and known PassWall2 routing.
2. Run the same one-command installer.
3. Confirm APK migrates both packages to named feed-managed entries and installs the new version.
4. Confirm `/root/xray-mitm-before-install-*.tar.gz` exists with mode `0600`.
5. Confirm the CA pair, service state, boot state, PassWall2 rules, node selection, and recovery state are unchanged.
6. Repeat health, route, and reboot checks.

Do not use a production router as the first test of a release.
