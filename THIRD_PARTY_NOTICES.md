# Third-party notices

## MITM-DomainFronting configuration

- Project: `patterniha/MITM-DomainFronting`
- Upstream version: `v23`
- Source: <https://github.com/patterniha/MITM-DomainFronting/tree/v23>
- Configuration source: <https://github.com/patterniha/MITM-DomainFronting/blob/v23/Xray-config/MITM-DomainFronting.json>
- License: GNU General Public License v3.0 (`GPL-3.0-only`)

The packaged sample is derived from that configuration. OpenWrt-specific hardening changes include localhost-only listeners, absolute certificate paths, and integration with a procd service and staged certificate lifecycle.

The GPL notice and source attribution must remain with redistributed builds. This file does not replace the full license text that accompanies a release.

## Other runtime projects

The packages declare or optionally integrate with separately distributed software:

- [Xray-core](https://github.com/XTLS/Xray-core), installed from an OpenWrt package feed.
- [OpenWrt](https://github.com/openwrt/openwrt) and [LuCI](https://github.com/openwrt/luci), which provide the operating system, APK build system, UI, and rpcd runtime.
- [PassWall2](https://github.com/xiaorouji/openwrt-passwall2), an optional runtime-detected integration that is not bundled or installed automatically.

Each project remains subject to its own license and release terms.
