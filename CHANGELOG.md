# Changelog

All notable user-facing changes to this project are recorded here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- Documented the local branch, router test, pull request, and signed release workflow.
- GitHub Releases now use the matching changelog section as their release notes.
- Consolidated routing into three ordered rules: **VPN Overrides**,
  **MITM-Compatible Services**, and **Regional Direct Access**. Checkboxes now
  add domain bundles to these rules instead of creating separate rules.
- Added optional Meta website and Fastly-backed website bundles, disabled by
  default until they are tested on the target devices.
- The first three-rule preview removes obsolete package-managed rules while
  preserving recognized user-created legacy rule definitions.

### Fixed

- Saved routing choices are derived from aggregate rule contents and the VPN
  selector prefers the active VPN Overrides assignment.
- Google Account routing can be selected independently of the Gemini bundle.
- Identical repeated previews no longer report a change only because of
  PassWall2's one-shot flush marker.

## [0.2.3] - 2026-09-09

### Changed

- Reworked the LuCI page around a four-step beginner setup guide and a simpler
  three-step PassWall2 routing assistant.
- PassWall2 nodes now use readable remarks and protocol details in selectors;
  internal UCI IDs are shown only when a node has no name.
- Added a recommended routing preset, aligned route cards, plain-language rule
  descriptions, an advanced-options disclosure, and clearer review/apply states.
- The four-step panel now identifies first-time setup separately from the
  preserved configuration shown after an update.
- Managed PassWall2 rules now use descriptive names, list their exact domain
  scope in LuCI, and keep checkboxes beside their text across LuCI themes.
- Changing any routing choice now invalidates the old preview immediately so a
  stale transaction cannot be applied accidentally.
- Routing inspection now reports whether the localhost MITM SOCKS node is ready,
  reusable, or will be created when Google MITM routing is selected.

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
