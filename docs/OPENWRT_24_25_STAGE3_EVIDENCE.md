# Stage 3 standalone-service evidence

Status: Stage 3 evidence record; this document does not declare public 24.10
support.

Audit baseline: `main` at
`a39ebcd4d06ed2c8bdb1c38055bf16b691b06429`.

## Scope and evidence boundary

Stage 3 covers the standalone Xray MITM service, certificate preservation,
health/service state, configuration preservation, recovery, and rollback. It
does not require PassWall2 and does not change routing, firewall, DNS,
certificate, signing, or publication policy.

The evidence levels remain separate:

1. accepted by the installer;
2. built by the appropriate official SDK;
3. dependency-resolved and integration-tested on the target family;
4. hardware-tested on a real supported device;
5. published as supported through an authenticated release feed.

Passing a package build or installer-selection test is not runtime or hardware
support evidence.

## 25.12.x / APK — bounded evidence passed

The exact protected PR #56 candidate was validated on the physical lab router
within the existing 25.12 contract:

- Candidate: `9b9849919a70533e122260d61bb667a02ff32dbb`.
- Protected signing run: `35514361371`.
- Protected artifact: `10606539043`, digest
  `sha256:dbf40ba64ebeecc6ed09269e5bb4541b8b36b3654856c7b0bdca4979cab02b02`.
- Device: ASUS TUF-AX4200, OpenWrt `25.12.5`, target `mediatek/filogic`,
  architecture `aarch64_cortex-a53`, `apk-tools 3.0.5`.
- The candidate was installed through the trusted signed APK repository path;
  direct local APK installation and `--allow-untrusted` were not used.
- The standalone package/service transaction preserved the configured,
  running, enabled, boot-enabled service state and kept recovery clear.
- The active certificate fingerprint, expiry, ownership, and key-mode boundary
  were preserved; private-key contents were not inspected or exposed.
- Project configuration, package-selection state, and unrelated router state
  were compared before and after the candidate transaction.
- Trusted rollback restored the prior package pair and the protected baseline;
  temporary repository state was removed.

This proves the bounded 25.12/APK existing-router service, preservation, and
rollback path. PassWall2 was present on the tested router, but no PassWall2
plan/apply operation is required for this Stage 3 result. Absence-of-PassWall2
behavior, external-service behavior, and every other 25.12 hardware target
remain outside this evidence.

## 24.10.x / IPK — runtime evidence unavailable

The official 24.10.8 `aarch64_cortex-a53` IPK lane passed its build and
dependency checks, and PR #56 adds fail-closed OPKG detection and explicit
authenticated test-feed inputs. No compatible 24.10 runtime target was
available for this stage.

The AX4200 is running 25.12.5 and was not downgraded. Local x86 emulation,
Docker, a VM, and mock-only runtime claims are outside the approved plan.
Therefore the following 24.10 claims remain unproven:

- native package installation and package scripts;
- service enable/start behavior and health checks;
- certificate and configuration preservation;
- native rollback and recovery on 24.10;
- hardware behavior and public support.

The correct current classification is: 24.10/IPK accepted by the installer
contract and built with dependency evidence; native runtime and hardware
support unproven.

## Resulting matrix

| Family | Package path | Build/dependency | Standalone runtime | Hardware | Public support |
| --- | --- | --- | --- | --- | --- |
| 24.10.x | OPKG/IPK | Proven for the recorded 24.10.8 target lane | Unproven | Unproven | Not claimed |
| 25.12.x | APK | Existing protected lane | Proven within the exact bounded evidence above | Proven on the AX4200 for that boundary | Existing 25.12 contract |

## Next gates

- Obtain a separately approved compatible 24.10 test target before claiming
  native 24.10 runtime or hardware support; do not replace it with emulation.
- Keep public 24.10 publication and production OPKG signing behind the later
  release and owner gates.
- The PassWall2 capability/fallback implementation is recorded in
  `docs/OPENWRT_24_25_STAGE4_EVIDENCE.md`. Its browser/LuCI gate and native
  24.10/IPK runtime remain unproven; do not treat this implementation evidence
  as a public support or release declaration. The capability remains optional
  and must not mutate routing for unknown schemas.

No router, package, signing, release, feed, or persistent configuration
mutation was performed by this documentation/evidence change.
