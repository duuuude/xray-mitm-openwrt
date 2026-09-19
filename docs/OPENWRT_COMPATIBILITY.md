# OpenWrt 24.10 and 25.12 compatibility contract

Status: Stage 0 design contract; not a public 24.10 support declaration.

Audit baseline: `main` at `24de3d1501103a3bb8089e2fe728e883256ca1ea`.

## Purpose

The compatibility initiative evaluates two official OpenWrt release families
for the same two project packages:

- OpenWrt 24.10.x using OPKG/IPK.
- OpenWrt 25.12.x using APK.

The product remains one standalone Xray MITM service and one LuCI management
interface. Package-manager differences, repository trust, platform detection,
and genuinely divergent system APIs may vary by family; certificate safety,
localhost-only service behavior, configuration preservation, and the LuCI →
rpcd/ucode → `xray-mitmctl` boundary remain shared invariants.

This document records the approved investigation and evidence boundary. It does
not claim that 24.10 packages, installation, runtime behavior, or public feed
publication are complete.

## Support contract

The current public product contract remains official OpenWrt 25.12.x with APK
packages. The 24.10 family is an approved legacy-compatibility target, not yet
a published support claim.

The owner-selected 24.10 label is:

> Legacy compatibility with limited security support. Compatibility work may
> target the latest available 24.10.x release, but the project does not promise
> upstream OpenWrt security maintenance after the 24.10 end-of-life date.

Before any public 24.10 release claim, the project must record the exact tested
release, evidence, maintenance boundary, and owner approval. Compatibility for
24.0–24.9, 25.0–25.11, snapshots, forks, or all hardware is not implied.

At the Stage 0 audit baseline, the reference releases are 24.10.8 and 25.12.5.
They must be revalidated when a build or release stage starts.

## Evidence levels

These claims are separate and must not be collapsed:

1. Accepted by the installer.
2. Built successfully by the appropriate official SDK.
3. Dependency-resolved and integration-tested on the target family.
4. Hardware-tested on a real supported device.
5. Published as supported through an authenticated release feed.

A family is not publicly supported merely because its package files build or its
major version is accepted by an installer.

## Initial matrix

| Family | Package manager | Reference release | First target | Current status |
| --- | --- | --- | --- | --- |
| 24.10.x | OPKG/IPK | 24.10.8 at audit time | `aarch64_cortex-a53` | Legacy target; build and runtime evidence pending |
| 25.12.x | APK | 25.12.5 at audit time | `aarch64_generic` CI and the AX4200's `aarch64_cortex-a53` | Existing public contract; retain current APK path |

The first 24.10 package lane should target `aarch64_cortex-a53` because that is
the physical lab-router architecture. `aarch64_generic` may be an additional
CI lane, but a generic build alone is not AX4200 evidence. Architecture-
independent project packages do not prove that Xray, geodata, ucode, LuCI, or
other dependencies exist for every target.

## Architecture and trust design

The intended shape is one installer with two independently authenticated
backends:

- 24.10: OPKG/IPK feed and its separately verified `usign` trust chain.
- 25.12: existing APK feed, key, repository, targeted upgrade, and rollback
  behavior.

The installer must detect the official release family, package manager,
architecture, required commands, and existing state before changing persistent
files. Unknown, mismatched, forked, or incompletely tested environments must
fail closed. No `--allow-untrusted`, disabled signature checks,
`--force-depends`, global upgrade, or replacement of official feeds is allowed.

Stage 1 must not add production IPK signing or publication. Stage 2 may split
test-only OPKG feed mechanics from production authenticated feed/installer work;
production signing remains protected and owner-gated.

## Standalone service and PassWall2 capabilities

PassWall2 is optional. Absence, incompatibility, uncertainty, or a failed
capability check must not prevent standalone installation, certificate
management, health checks, service operation, or truthful diagnostics.

The capability model is separate from package-manager detection:

- `standalone_service`: installed, configured, running, and healthy.
- `passwall2_present`: absent, present, or unknown.
- `passwall2_schema`: verified, unsupported, or unknown.
- `passwall2_inspect`: truthful read-only inspection available or unavailable.
- `passwall2_plan_apply`: enabled only for a fully tested safe combination.
- `manual_routing_guide`: informational only and clearly not configured or
  verified.
- `recovery_pending`: an independent safety state that cannot disappear merely
  because automatic integration is disabled.

Unknown or unsupported PassWall2 states must disable automatic plan/apply and
fail closed without hiding an existing recovery obligation. The current
localhost-only listener contract remains unchanged; compatibility work must not
expose it to the LAN or WAN as a shortcut.

## Ordered implementation stages

Only one stage is active at a time, and each stage is a separate reviewed PR.

### Stage 0 — contract and design

This documentation PR records the support label, matrix, evidence levels,
architecture, trust boundaries, standalone/PassWall2 model, validation budget,
and ordered work below. It changes no product behavior. After merge, recheck
`main` and stop before Stage 1.

### Stage 1 — 24.10 package build

Build `xray-mitm` and `luci-app-xray-mitm` as IPKs with an official 24.10 SDK,
prove dependency resolution for the declared target, and preserve the existing
25.12 APK lane. Do not add production feed publication or signing here.

### Stage 2 — OPKG feed and dual-backend installer

Use separate test-only feed mechanics and protected production trust/publishing
work as needed. Add an OPKG backend without weakening the existing APK path.

### Stage 3 — standalone MITM

Prove service, certificate, health, configuration, and recovery behavior without
requiring PassWall2 on both families.

### Stage 4 — PassWall2 capability probe and safe fallback

Detect tested schemas and expose truthful read-only diagnostics/manual guidance;
unknown combinations must not mutate routing.

### Stage 5 — optional automatic PassWall2 integration

Enable plan/apply only for explicitly tested combinations with complete
transaction, recovery, rollback, and state-preservation evidence.

### Stage 6 — evidence and release contract

Document exact tested releases, architectures, package/feed identity, installer
behavior, runtime gates, limitations, and the final owner-approved support
claim. Production signing and publication remain separate protected actions.

## Validation and budget

The fast local loop uses the native Apple Silicon Mac for offline tests,
fixtures, static checks, and documentation validation. No local x86 emulation,
Docker VM, paid API, extra credits, separately paid cloud VM, or paid runner is
required for that loop. Bounded GitHub-hosted jobs within the available free
allowance are permitted and may be required for official SDK/package builds.

Official SDK/package builds that need Linux or x86 tooling belong in bounded
GitHub-hosted jobs within the available free allowance. A slow or unavailable
environment must be reported, not bypassed by purchasing capacity.

The existing AX4200 file-staging and browser loop remains useful for current
25.12 LuCI/service evidence. It does not prove 24.10/IPK compatibility. No
firmware downgrade is part of this initiative; 24.10 runtime evidence requires
a separately approved compatible test target.

## Stage 0 acceptance and stop condition

Stage 0 is complete only when the repository records:

- the two-family support matrix and legacy 24.10 security boundary;
- supported versus untested architectures and releases;
- independent APK and OPKG package/feed trust designs;
- standalone and PassWall2 capability states;
- the ordered PR sequence and exact evidence gates;
- the no-emulation local loop and bounded CI plan;
- owner-gated signing, release, router, firmware, and public-support actions;
- no product, installer, package, CI, signing, release, or router changes.

After the documentation is independently reviewed and owner-approved for
merge, re-read current `main`. Do not begin Stage 1 in the same PR or create a
bookkeeping-only reconciliation PR for this Stage 0 change.

## Non-goals

- Supporting every OpenWrt version, snapshot, fork, or hardware target.
- Downgrading or reflashing the AX4200.
- Replacing real-router/browser evidence with a local emulator.
- Exposing the localhost MITM listener or changing global firewall/DNS policy.
- Combining package builds, installer changes, production signing, and public
  publication in one PR.
- Claiming 24.10 public support before the later evidence stages are complete.
