# Local v0.4.5 lab signing

This is a private, local-only procedure for the exact already-built v0.4.5
APK artifact. It does not build packages, upload files, create a GitHub
release/tag, publish the feed, or install anything on a router.

The source repository is public. GitHub Free supports required-reviewer
environments on public repositories, but a signed Actions artifact in this
repository would be available to repository readers. The signed lab bundle
therefore stays on the local machine instead of being uploaded. See GitHub's
[environment plan limits](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments)
and [artifact download access](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/download-workflow-artifacts).

## Pinned source

- Repository: `duuuude/xray-mitm-openwrt`
- Workflow: `Build OpenWrt APKs` (`351137159`)
- Successful run: `36903522011`, attempt `1`, event `push`, branch `main`
- Source commit: `135bae3e54adb7d9181f79e08bd863bbf778fc8f`
- Artifact: `11185431993`
- Artifact name: `xray-mitm-openwrt-25.12.5-aarch64_generic-135bae3e54adb7d9181f79e08bd863bbf778fc8f`
- Artifact digest: `sha256:902fcd2166b06bb695a01040415ef5632102b64d42f5a002cea87e9831152d9d`
- Release / architecture: `25.12.5` / `aarch64_generic`
- APKs and verified `PACKAGE_SHA256SUMS`:
  - `luci-app-xray-mitm-26.269.77380~a3bf576.apk` — `2ee473c8db32c62083c9945f2bb57aa1c93773833bcb2860e98153daff47bcdc`
  - `xray-mitm-0.4.5-r1.apk` — `a03f2758867ddc38eb6ace592b57bea300b4f58913f0dfb19497296a7de71f8d`
- Trusted feed public-key SHA-256: `3e0dc07ffef69d1512500b6add486381d8c261a8ec3fcce54fa403b35320df8a`

The artifact expires at `2026-10-31T18:36:30Z`. Its downloaded archive SHA-256
matched GitHub's digest, and the embedded source/run metadata, package list,
and package checksums passed `scripts/verify-promotion-artifact.sh`. The helper
fails if GitHub says it is expired or if the run, artifact identity, bundle
contents, or checksums differ from these pins. The LuCI APK's `a3bf576`
filename suffix is its package source revision; the enclosing artifact is
bound to main commit `135bae3…`. It does not silently choose a newer build.

## Requirements and boundaries

- macOS or another host with Python 3, authenticated `gh`, Docker, and the
  repository's public feed-verification key.
- A local copy of the matching signing private key is required only for the
  `sign` step. Keep it outside both the repository and the temporary session,
  do not paste or upload it, and set its permissions to owner-only (`0600`).
  The helper refuses a key path inside the session, and cleanup refuses to
  remove unexpected files. If the owner does not already have the private key
  locally, stop; this helper cannot retrieve a GitHub Actions secret.
- The Docker image is pinned by digest and runs without network access. The
  private key is mounted read-only and is never copied to the output bundle.
  Before starting it, the helper rejects `DOCKER_HOST`/`DOCKER_CONTEXT`
  overrides and requires the selected Docker context to use a local Unix
  socket; remote daemons are not supported.
- The command asks for the exact confirmation `SIGN ONLY packages.adb`.
  Only `packages.adb` may change; APK bytes and other input files are checked
  unchanged, and the signed index is verified with the repository public key.
- Staging and output are under a mode-`0700` temporary session directory;
  files are mode `0600`. A 24-hour cleanup target is a manual policy, not an
  automatic expiry. Use the exact-session cleanup command below when finished.
- Tests use synthetic bundles and a fake signer; they do not use a real key or
  prove a real signature. This guide and a passing test suite do not authorize
  signing, router transfer/install, release, or publication.

## Prepare and inspect the exact unsigned bundle

From the repository root:

```sh
python3 scripts/lab_sign_v045.py prepare
```

The helper prints the private temporary session path and the `unsigned`
subdirectory. Inspect the printed provenance and files locally. Do not copy
the bundle into the repository or a public location.

## Sign locally, only after separately deciding to do so

```sh
python3 scripts/lab_sign_v045.py sign \
  --session-dir /exact/path/printed/by/prepare \
  --key /exact/path/to/your/local/private-signing-key.pem
```

The key must be a regular file owned by the current user with mode `0600`,
stored outside the repository and the printed temporary session directory.
The helper rechecks the live pinned GitHub run and artifact before signing.
It also requires this repository to be clean, checked out on `main`, and at
the exact commit currently named by GitHub's live `main` ref; it checks this
again after the signing container exits and records the tool commit.
The signed output is `signed-bundle` inside the same session directory. It
contains a provenance record, original-build checksums, updated bundle
checksums, the public verification key, and the signed `packages.adb`; it does
not contain the private key.

## Remove the local session

```sh
python3 scripts/lab_sign_v045.py cleanup \
  --session-dir /exact/path/printed/by/prepare
```

The helper displays the exact deletion phrase before removing only that
verified session directory. This cleanup is intentionally explicit and is not
performed by CI.
