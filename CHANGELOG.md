# Changelog

All notable user-facing changes to this project are recorded here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- Documented the local branch, router test, pull request, and signed release workflow.
- GitHub Releases now use the matching changelog section as their release notes.

## [0.2.3] - 2026-09-09

### Fixed

- PassWall2 refuses to apply a Google MITM route while the standalone MITM
  service is stopped, preventing traffic from being sent to an unavailable
  local SOCKS listener.
- PassWall2 child processes no longer inherit the routing transaction lock.
- LuCI explains the stopped-service requirement and disables unsafe previews.

## [0.2.2] - 2026-09-09

### Fixed

- The one-command installer now upgrades existing `xray-mitm` and
  `luci-app-xray-mitm` installations to the current signed-feed versions.
- Updates remain limited to the two project packages and their required dependencies.

## [0.2.1] - 2026-09-09

### Fixed

- PassWall2 routing previews now preserve the selected nodes and managed-rule choices.
- Preview staging now produces an applicable private UCI delta without modifying the
  saved PassWall2 configuration.
- PassWall2 node labels use available remarks and protocol details instead of opaque
  section IDs where possible.
- Managed-rule checkboxes are aligned with their labels in LuCI.

## [0.2.0] - 2026-09-09

### Added

- Authenticated APK installation and repeatable updates through a signed project feed.
- A checksum-pinned public one-command installer for macOS, Windows, and router shells.
- Protected GitHub Actions publishing for signed feed metadata, packages, Pages, and
  GitHub Release assets.

### Fixed

- Release checksum filenames now match GitHub's uploaded APK asset names.

## [0.1.0] - 2026-09-06

### Added

- Standalone Xray MITM Domain Fronting service packaging for OpenWrt.
- LuCI service, certificate lifecycle, health-check, and optional PassWall2 controls.
- English and Persian installation and operating instructions.

[Unreleased]: https://github.com/duuuude/xray-mitm-openwrt/compare/v0.2.3...HEAD
[0.2.3]: https://github.com/duuuude/xray-mitm-openwrt/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/duuuude/xray-mitm-openwrt/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/duuuude/xray-mitm-openwrt/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/duuuude/xray-mitm-openwrt/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/duuuude/xray-mitm-openwrt/releases/tag/v0.1.0
