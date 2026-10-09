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

### Disposable SDK signing component

`python3 tests/test_sdk_signing.py --sdk` executes the publisher's actual
signing and always-cleanup shell blocks with freshly generated disposable keys
and two tiny unsigned noarch APK fixtures. It checks strict index verification,
unchanged package bytes, readable outputs, mode-0600 key ownership/access, and
cleanup after success, checksum failure, wrong working directory/executable,
non-owner access and a mismatched public key. It does not sign a product feed,
read production keys, publish, install, or connect to a router.

Use a running local Unix-socket Docker daemon, Bash and OpenSSL, with the exact
publisher SDK digest already cached. The test never pulls an image or changes
Docker configuration; a missing runtime/image fails, not skips. Containers have
no network; disposable files and specifically named test containers are removed
on success/failure. The standalone component has a seven-minute execution budget
plus bounded cleanup. Without `--sdk`, only offline contract tests run and SDK
execution is explicitly reported **NOT RUN**.

Desktop bind-mount permission mapping can differ from a native Linux host.
The component measures the mounted key's owner/mode and attempts a real discarded
read as a different UID; if the host permits it, the permissions case fails closed.
Do not relax the assertion or call this local result green. Native Linux CI is
the authoritative host/container permission gate for the Linux publisher.

The `Disposable SDK signing regression` workflow runs on relevant signing,
publisher and component-test changes only, using the exact PR head or main SHA.
It pulls the pinned image on the existing Linux CI runner before executing the
secret-free component. Ordinary documentation-only changes do not schedule it.
Green component evidence is not production signing, publication, native-router
qualification or permission to bypass separate release/owner gates.

## 2. Reusable local AX4200 loop

The repository includes `scripts/router-local-test.sh` for the lab-router loop.
It uses SSH and `scp -O`; it does not require Docker, GitHub Actions, an APK
build, or a router-side package feed. The script protects the original service,
RPC, and LuCI candidate files once, stages the exact local candidate with the
correct modes, and can restore those originals without restarting Xray or
changing PassWall2 routing.

**MAC:**

```sh
cd "/path/to/xray-mitm-openwrt"
sh scripts/router-local-test.sh validate
sh scripts/router-local-test.sh config-validate
sh scripts/router-local-test.sh stage
sh scripts/router-local-test.sh check
sh scripts/router-local-test.sh restore
sh scripts/router-local-test.sh check
```

`stage` runs the offline validator again by default. After a separate successful
validation, `ROUTER_SKIP_VALIDATE=1` may be used only when the candidate has not
changed. The default connection is `root@192.168.1.1` with
`~/.ssh/xray-mitm-ax4200`; set `ROUTER_HOST`, `ROUTER_USER`, `ROUTER_SSH_KEY`, or
`ROUTER_BACKUP_DIR` when the lab setup differs. The protected backup stays on
the router and contains code only; certificates, private keys, credentials, and
router configuration are never copied into the repository.

Before staging, an existing backup must match all six current live files and
the `ui.js` presence marker byte-for-byte. A stale or older backup is rejected
without refreshing or using it; choose a new, explicit `ROUTER_BACKUP_DIR`
only after confirming the current router files are the intended baseline.
The backup path must be beneath existing root-owned directories that are not
group/other writable. Existing backup directories and every contained entry
must also be root-owned and not group/other writable; symlinked path components,
unexpected entries, and unsafe permissions are rejected before staging or
restore. The helper does not create missing parent directories. Keep the
default `/root/xray-mitm-local-backup`, or prepare another protected parent as
root before selecting a custom path.
Before any live file is replaced, `stage` records the exact candidate hashes
in `ACTIVE_STAGE` beside that backup. `restore` accepts only files matching
either the saved baseline or that staged candidate, and refuses to overwrite
unrelated newer router content. Stage and restore replace each file atomically;
a failed restore keeps `ACTIVE_STAGE` for diagnosis and retry.

After `stage`, reload every affected LuCI page in the real desktop browser,
exercise the controls, and inspect the browser console. Run `check` while the
candidate is staged, then run `restore` and `check` again. Apply a live routing
preview only as a separate, deliberate test after the candidate has passed the
browser gate.

This file-level staging loop is for fast LuCI and service-interface testing. A
public release still needs the exact successful main-branch APK build and the
signed-feed checks below. The tag workflow must promote those exact package
bytes and sign only the package index; it must not rebuild the packages.

## 3. Recovering from a failed CI run

When GitHub Actions fails, read the failed step before changing code. Reproduce
the named test locally, make the smallest fix, and run the complete validation
again. If the local shell cannot find Node.js, pass the bundled or installed
executable explicitly:

**MAC:**

```sh
NODE_BIN=/path/to/node sh scripts/validate-release.sh
```

Check the remote before pushing. The canonical checkout uses `origin` for the
verified GitHub repository; confirm its exact URL before pushing. After every
follow-up commit, repeat the applicable local tests and obtain explicit
project-owner approval before pushing it.

## 4. Local LuCI browser gate

This gate is required for every change that can affect a LuCI page, including its
JavaScript, templates, styles, RPC data, and ACL access.

1. Install or stage the exact release candidate on the lab router.
2. Open each affected page in a local desktop browser and reload it directly to
   bypass stale LuCI JavaScript.
3. Confirm the full page renders without an error notification or blank view.
4. Exercise all affected controls and state transitions. For routing changes,
   verify selection persistence, review/preview, apply, and return-to-page state.
5. Inspect the browser console after loading and interacting; confirm no new
   JavaScript errors were recorded.
6. Confirm the CA, standalone service state, boot state, and PassWall2 routing were
   preserved unless the release intentionally changes them.
7. Save the tested commit, candidate version, page, control results, console result,
   and any screenshot in the release or pull-request evidence.
8. Present the exact tested UI candidate to the project owner and record explicit
   visual approval before pushing, merging, tagging, or publishing it.

A syntax check, mocked frontend test, successful APK build, or green GitHub Actions
run is insufficient by itself. The owner's silence is not UI approval. Do not push,
merge, tag, or publish until both the browser test and visual approval pass.

## 5. Signed publishing checks

Before the tag:

1. Confirm `CHANGELOG.md` has a dated section for the intended version and no released entries remain under `Unreleased`.
2. Confirm `PKG_VERSION` is intended, `PKG_RELEASE` is `1`, and the tag will be exactly `v${PKG_VERSION}`.
3. Review the full diff and confirm only `keys/xray-mitm-feed-v1.pem` is public-key material.
4. Confirm the private key exists only in protected storage and the `signed-feed` environment secret.
5. Confirm required environment reviewers and GitHub Pages are configured.
6. From the clean, synchronized `main` branch, run `sh scripts/release-preflight.sh`.
7. Confirm a successful `Build OpenWrt APKs` push run exists for the exact
   release commit, and record its run ID, artifact name, source commit, and
   package checksums.

After approving the tagged workflow:

1. Confirm the protected job proves the private/public key match.
2. Confirm the tag workflow downloaded the recorded main-build artifact for the
   exact commit and verified its package checksums before signing.
3. Confirm exactly one core APK, one LuCI APK, and one `packages.adb` are
   present, and that the package bytes match the main-build checksums.
4. Confirm the protected job signed only `packages.adb` and did not rebuild the
   packages.
5. Confirm the protected signing/verifier SDK image uses the reviewed immutable
   digest `sha256:d7759c08b2c0b0ffe57719bd8a293543708cbc27b18941478ebeae04c42986ed`.
6. Confirm the GitHub Release also contains `SHA256SUMS`, `SOURCE_COMMIT`,
   `RELEASE_COMMIT`, build provenance, `PUBLIC_KEY_SHA256`, and the public key.
7. Confirm Pages serves the key and `feed/25.12/all/packages.adb` over HTTPS.
8. Independently verify key SHA-256 `3e0dc07ffef69d1512500b6add486381d8c261a8ec3fcce54fa403b35320df8a`.

## 6. Clean-router installation

Use a disposable or lab router:

1. Confirm official OpenWrt 25.12.x with APK; use 25.12.5 for the public clean-router baseline.
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

## 7. Existing-router update

1. Start with a working prior version, active CA, boot setting, and known PassWall2 routing.
2. Run the same one-command installer.
3. Confirm APK migrates both packages to named feed-managed entries and installs the new version.
4. Confirm only the three newest `/root/xray-mitm-before-install-*.tar.gz`
   project backups are retained and each has mode `0600`.
5. Confirm the CA pair, service state, boot state, PassWall2 rules, node selection, and recovery state are unchanged.
6. Repeat health, route, and reboot checks.

Do not use a production router as the first test of a release.

## 8. Protected candidate package-installation evidence

Use this procedure when validating an exact protected PR artifact on a real
OpenWrt router. It is a candidate-validation procedure, not a release or
publishing procedure.

Before the first package-manager command:

1. Verify the exact PR, candidate commit, base commit, artifact digest, package
   names, package checksums, signed `packages.adb`, and trusted public-key
   fingerprint on both the Mac and the router. Never substitute a rebuilt or
   similarly named artifact.
2. Create a protected, router-local evidence directory with mode `0700` and
   capture complete pre-test copies of `/etc/apk/world`, the relevant
   repository configuration, and the project configuration files whose
   preservation is part of the test. Capture the file mode, owner, size, and
   SHA-256 for each copy. A hash without a protected baseline copy is
   insufficient for proving exact recovery. Do not transfer or print copies
   that contain credentials, node details, subscription URLs, or other secret
   values.
3. Record the read-only service, certificate, PassWall2, routing, firewall,
   DNS, recovery-marker, installed-package, and pending-UCI state. The router
   must start with no unexplained pending UCI changes.
4. Keep fixture tests off the live router. Run synthetic partial, wrong-target,
   invalid-group, and legacy-rule cases in the repository's isolated tests. If
   a live diagnostic genuinely requires temporary UCI state, use an isolated
   temporary delta directory, verify that it contains only the declared test
   paths, preserve a root-only recovery copy, and require explicit cleanup and
   post-cleanup verification.

During installation and rollback:

- Require separate owner approval for the exact transfer, candidate
  installation, and rollback mutation.
- Use only the verified signed repository path. Do not install local APK files
  directly and never use `--allow-untrusted`.
- Do not apply routing, change firewall or DNS, replace certificates, restart
  services, reboot, or run synthetic fixture mutations as part of package
  installation unless separately approved and explicitly in scope.
- Record the exact package-manager transaction result and stop on any trust,
  dependency, package-identity, or state-preservation failure.

### APK protected configuration: expected delta, not automatic failure

APK can preserve a modified active conffile and place the package's default in
`/etc/config/xray-mitm.apk-new`. Existence alone is not an installation failure.
See the [APK configuration preservation documentation](https://docs.alpinelinux.org/user-handbook/0.1a/Working/apk.html).
Declare this possible delta BEFORE an owner-approved upgrade; do not retroactively
clear a stopped historical test. Capture its pre-existing presence/absence and,
if present, type, SHA-256, size, numeric owner/group and mode in the protected
baseline. Never overwrite, merge, delete or activate a pre-existing file.

The sole newly created config-file exception is this exact path, a non-symlink
regular file owned by root/root with mode `0600`, whose size and SHA-256 match
the default extracted from the independently verified exact signed core APK.
A source-tree default alone is not artifact proof. Bind the default evidence to
the exact candidate and package digest; independently verify signed index,
trusted public key, package version and provenance before using it. The active
config must remain byte-for-byte identical with unchanged type/owner/mode, and
the complete relevant config inventory must have no other unexplained deltas.
No automatic default merging or `.apk-new` suppression is permitted.

On the MAC, classify an already collected secret-free metadata snapshot with:

```sh
python3 scripts/apk-config-delta.py --phase upgrade --snapshot /absolute/path/evidence.json \
  --expected-candidate FULL_VERIFIED_CANDIDATE_SHA \
  --expected-package VERIFIED_CORE_APK_SHA256
```

The snapshot has exactly these fields: `config_path` (the exact active path),
`candidate_sha` (40 lowercase hex), `package_sha256` (64 lowercase hex),
`package_default` (`sha256`, positive `size`), `active_before`, `active_after`,
`apk_new_before`, `apk_new_after`, and `other_config_deltas` (empty list only
after complete comparison). Each file metadata object has exactly `kind`
(`regular`), `sha256`, `size`, `uid`, `gid`, and `mode` (four octal digits such
as `0600`); only the two `.apk-new` objects may be null, meaning confirmed
absence, never an omitted observation. Include no configuration contents.

Expected identities must come from the independently verified assignment and
signed package evidence, not be copied from the snapshot being checked. Both
required inputs must match the snapshot exactly; a different valid digest also
returns `HOLD`. Positive output includes the matched `candidate_sha` and
`package_sha256` for attribution. This proves identity consistency, not trust.
`EXPECTED_APK_NEW` or `UNCHANGED` classifies supplied config evidence only.
The helper does not collect evidence or verify its authenticity/signatures;
it does not authorize mutations or prove installation/runtime/browser PASS.
Missing or malformed evidence, changed active config, an altered pre-existing
file, wrong new-file bytes/metadata, or other unexplained config deltas is
`HOLD` (exit 1): stop and follow the previously approved recovery procedure.
Continue separately required service/CA/PassWall2/routing/firewall/DNS/world,
package-version and browser checks only within existing owner scope. Account
for intentional package-world changes separately; config classification does
not approve them.

For rollback, use the same checker with `--phase rollback` and the actual
pre-transaction baseline. It allows NO new-file exception: presence, absence,
bytes and metadata must match baseline. A leftover expected upgrade default
still prevents exact restoration PASS. Preserve evidence and report the
discrepancy; archive/removal needs an explicitly approved recovery/cleanup
scope and independent post-action verification. This rule is not cleanup
authority and does not waive any of the restoration requirements below.

After rollback:

1. Recheck package versions, service state, certificate metadata, PassWall2
   state, pending UCI state, recovery markers, and all preserved configuration
   files.
2. Compare the complete protected baseline copies byte-for-byte. In particular,
   `/etc/apk/world` must match the captured pre-test copy; matching package
   names or a matching hash recorded without the original file does not prove
   exact package-manager recovery.
3. Confirm temporary UCI deltas are absent and that no persistent configuration
   file changed. Do not delete evidence directories until their contents and
   final hashes have been recorded.
4. If any required baseline copy is missing, any comparison differs, or any
   temporary UCI state remains, report `FAIL`. Do not infer recovery, edit the
   package-world file, or waive the discrepancy without a separately approved
   evidence decision.

The final report must distinguish: candidate installation passed, rollback
passed, exact recovery passed, and behavior that remains unproven. A successful
package transaction alone is not a clean live-validation result.
