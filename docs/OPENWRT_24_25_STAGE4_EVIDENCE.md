# OpenWrt 24.10/25.12 Stage 4 Evidence

Status: bounded implementation and 25.12/APK runtime evidence recorded; the
LuCI/browser gate and native 24.10/IPK runtime remain unproven.

Evidence date: 2026-09-21

## Exact candidate and protected artifact

- Repository: `duuuude/xray-mitm-openwrt`
- Pull request: [#59](https://github.com/duuuude/xray-mitm-openwrt/pull/59)
- Candidate: `a1151639d763b55631af1e309c9373d62b0db4b8`
- Base: `39368c41d91ab0625bcb1b8fd6e318348d99c518`
- Protected signing run: [35594300825](https://github.com/duuuude/xray-mitm-openwrt/actions/runs/35594300825)
- 24.10/IPK CI run: [35591319291](https://github.com/duuuude/xray-mitm-openwrt/actions/runs/35591319291)
- 25.12/APK CI run: [35591319312](https://github.com/duuuude/xray-mitm-openwrt/actions/runs/35591319312)
- Artifact ID: `10638976106`
- Artifact name: `xray-mitm-pr-59-a1151639d763b55631af1e309c9373d62b0db4b8`
- Archive SHA-256: `b70d083a2fe4fee1ec09f5bbc809db2dd668db3a7a5b7df5bef25fbd36038573`
- Artifact purpose: protected PR candidate validation, not a release

The artifact metadata matched the candidate, base, and PR number. Its inventory
contained exactly the two expected APKs, the signed `packages.adb` index, the
pinned public key, metadata, and checksums.

Candidate package checksums:

- `xray-mitm-0.4.4-r2.apk` —
  `a27e6fe963c9907bb137fb6f7287812a44654c957515ac9474cce034c5c34c8c`
- `luci-app-xray-mitm-26.264.30328~e03b15f.apk` —
  `c92985f81263678c286afb850a59911bfa5d3ab40c73e6b334ddc59238398dc1`
- `packages.adb` —
  `a4cb7566b40220f30513640d038e04291ab01419bc8b7a6e05e689a180620e4a`
- `xray-mitm-feed-v1.pem` —
  `3e0dc07ffef69d1512500b6add486381d8c261a8ec3fcce54fa403b35320df8a`

The archive and `SHA256SUMS` were independently verified. The router trusted
the matching public key, and signed-repository simulation and installation used
the repository trust path only. No direct APK installation and no
`--allow-untrusted` operation was used.

## Bounded AX4200 runtime evidence

Target: ASUS TUF-AX4200, OpenWrt `25.12.5`
(`r33051-f5dae5ece4`), `mediatek/filogic`,
`aarch64_cortex-a53`, apk-tools `3.0.5`, firewall `fw4`.

The exact candidate pair was installed through the trusted temporary
repository:

- `xray-mitm-0.4.4-r2`
- `luci-app-xray-mitm-26.264.30328~e03b15f`

The service stayed running, enabled, configured, and master-enabled. The
certificate fingerprint and expiry were unchanged. PassWall2 capability
inspection against the real configuration reported the supported schema,
compatibility, writability, shunt/VPN availability, no pending changes, no
recovery state, and truthful routing inventory. No plan, apply, rollback,
recovery, or routing mutation was invoked. Protected configuration, generated
DNS, resolver, firewall, network, and certificate state remained unchanged;
the repaired DNS baseline remained `localservice=1`, `noresolv=1`, and
`server=127.0.0.1#2005`.

WAN, router DNS, and LAN DNS checks passed. The exact prior signed package pair
was then restored through the trusted rollback repository:

- `xray-mitm-0.4.4-r1`
- `luci-app-xray-mitm-26.256.24801~dcd585a`

The protected baseline manifest and package, service, certificate, PassWall2,
routing, firewall, DNS, WAN, LAN, and recovery checks returned to baseline.
Temporary validation files were removed; the existing protected router backup
was untouched.

## Unproven gates and limits

The candidate changed LuCI files, so the real browser gate was required. Chrome
reached the exact LuCI page but stopped at
`NET::ERR_CERT_COMMON_NAME_INVALID` because the certificate identified
`OpenWrt`, not `192.168.1.1`. No warning bypass, trust-store change, HTTP
downgrade, or certificate mutation was allowed. LuCI rendering, control/state
exercise, browser-console behavior, and owner visual approval therefore remain
unproven.

Native OpenWrt 24.10/IPK/OPKG installation, runtime, hardware, and rollback
behavior also remain unproven. This record is bounded evidence for the PR #59
implementation and the tested 25.12/APK path; it is not a public 24.10 support
claim, a completed browser qualification, or a release authorization.
