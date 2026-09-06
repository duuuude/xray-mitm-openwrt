# Release testing

The offline validator is the first release gate. It checks the expected two-package layout; parses JSON files including `config.json.example`; verifies the fixed localhost listeners, certificate paths, disabled first-run state, exact core and LuCI dependency tokens, narrow ACL split, noarch declarations, and pinned workflow actions; and rejects common router exports, package binaries, certificate/key files, and private-key PEM content. The wrapper also runs isolated certificate lifecycle tests with real OpenSSL (generation, permissions, public-only export, matching import, and mismatched-key rejection), a PassWall2 transaction fixture (preview, apply, exact rollback, pending-change refusal, privacy, and interrupted recovery), exercises the disabled-versus-explicit init enable behavior in temporary storage, parses every installed shell script, and checks the LuCI JavaScript syntax when Node.js is available.

**MAC:**

```sh
cd "/path/to/xray-mitm-openwrt"
sh scripts/validate-release.sh
```

The structural checks use only Python's standard library and the shell checks use the host's `/bin/sh`. Node.js is optional locally and present on the GitHub-hosted runner. The validation does not connect to a router, alter network settings, or need internet access.

GitHub Actions runs the same test before starting the OpenWrt SDK build. A successful SDK job must produce exactly one `xray-mitm` APK, one `luci-app-xray-mitm` APK, `SHA256SUMS`, `LICENSE`, `THIRD_PARTY_NOTICES.md`, the English and Persian README files, and a `SOURCE_COMMIT` file.

Before publishing a tagged build, also perform a disposable-router or lab-router test:

1. Confirm the firmware reports OpenWrt 25.12.5 or later and uses APK.
2. Confirm installation leaves the service stopped, both the UCI master and `boot_enabled` switches at zero, and no `S98xray-mitm` or `K10xray-mitm` boot links; also confirm it does not change PassWall2, firewall, DNS, or routing.
3. Generate a candidate CA, download the public certificate, and confirm no private-key download exists.
4. Confirm the private key on the router is owned by `root` and has mode `0600`.
5. Activate the candidate, start the service, and run the built-in health check.
6. Preview PassWall2 changes and compare the preview with a fresh UCI backup before applying.
7. Exercise rollback and confirm the original rule order and node assignments return exactly.
8. Confirm listeners remain bound only to `127.0.0.1`.
9. Verify a selected MITM domain shows the local CA issuer while an unrelated control domain shows its normal public issuer.
10. Confirm the root-only PassWall2 rollback snapshot is not exposed through LuCI and remember that it can contain node credentials.
11. Inspect the final Git diff and release archive again for secrets.

Do not use a production router as the first test of a new release.
