# Xray MITM Domain Fronting for OpenWrt

**Version:** `v0.4.3` · **Instructions:** English | [فارسی](README.fa.md) · **Project:** [Changelog](CHANGELOG.md) | [Contributing](CONTRIBUTING.md)

This project adds a standalone Xray MITM-DomainFronting service, a LuCI dashboard, and optional PassWall2 routing to official OpenWrt 25.12 APK-based routers.

For most users:

1. Install or update with one command.
2. Open LuCI and go to **Services → MITM Domain Fronting**.
3. In **Basic**, select **Set up automatically**.
4. Download and trust the public certificate.
5. Choose your existing VPN and review the recommended routing.
6. Apply the routing and select **Run check**.

> [!CAUTION]
> MITM software can decrypt HTTPS traffic from devices that trust its certificate. Use it only on networks and devices you own or are authorized to manage. Install only `mycert.crt` on clients. Keep `mycert.key` on the router and in protected backups.

## Requirements

- Official OpenWrt 25.12.5 or a later 25.12 maintenance release, with `apk` and LuCI.
- Internet access from the router to GitHub and GitHub Pages.
- PassWall2 for automatic routing. It is not required for the MITM service itself.
- A working PassWall2 shunt profile and VPN node for VPN-routed services.

## Compatibility

- Official OpenWrt 25.12.x using APK packages: `xray-mitm` and `luci-app-xray-mitm`.
- Tested hardware: ASUS TUF-AX4200. Other hardware may work, but is not on the tested list.

## Install or update

The same command is used for a first installation and later updates. Replace `192.168.1.1` if your router uses another address.

**MAC:**

```sh
ssh root@192.168.1.1 'wget -qO /tmp/install-xray-mitm.sh https://duuuude.github.io/xray-mitm-openwrt/install.sh && printf "%s  %s\n" "8af96edc133c01a7e9d0a8f4673b7225c47322d73874c05a9c4a0133f3058405" "/tmp/install-xray-mitm.sh" | sha256sum -c - && sh /tmp/install-xray-mitm.sh'
```

**WINDOWS PC (PowerShell):**

```powershell
ssh.exe root@192.168.1.1 'wget -qO /tmp/install-xray-mitm.sh https://duuuude.github.io/xray-mitm-openwrt/install.sh && printf "%s  %s\n" "8af96edc133c01a7e9d0a8f4673b7225c47322d73874c05a9c4a0133f3058405" "/tmp/install-xray-mitm.sh" | sha256sum -c - && sh /tmp/install-xray-mitm.sh'
```

**ROUTER** if you are already connected through SSH:

```sh
wget -qO /tmp/install-xray-mitm.sh https://duuuude.github.io/xray-mitm-openwrt/install.sh && printf '%s  %s\n' '8af96edc133c01a7e9d0a8f4673b7225c47322d73874c05a9c4a0133f3058405' '/tmp/install-xray-mitm.sh' | sha256sum -c - && sh /tmp/install-xray-mitm.sh
```

The installer checks the OpenWrt release, verifies the installer checksum and signed feed, creates a protected backup, and updates only the project packages. It does not install PassWall2, create a certificate, start MITM, or change routing.

The pinned installer SHA-256 is `8af96edc133c01a7e9d0a8f4673b7225c47322d73874c05a9c4a0133f3058405`.

When it finishes, open LuCI over **HTTPS** at **Services → MITM Domain Fronting**.

## First-time setup

This flow is for a fresh installation. Updates preserve the configuration, active certificate, service state, and PassWall2 routing; repeat setup only if LuCI reports that something is missing.

### 1. Set up the router

In **Basic → Setup**, select **Set up automatically**.

This prepares the default configuration when needed, creates and activates a certificate when needed, starts MITM, and enables startup after reboot. It preserves a valid existing configuration and certificate and does not install PassWall2.

### 2. Download and trust the public certificate

In **Basic → Setup**, select **Download public certificate**. Install only `mycert.crt` on devices that should use MITM; the private key stays on the router.

- **macOS:** open it, add it to Keychain Access, and set it to **Always Trust**.
- **Windows:** open it, select **Install Certificate**, and place it in **Trusted Root Certification Authorities**.
- **Android:** open Security settings, choose **Install a certificate**, and install it as a CA certificate.

Menu names can vary by operating-system version. Firefox may use a separate certificate store. Some native applications ignore user-installed certificates or use certificate pinning; test a browser first.

### 3. Configure recommended routing

If you do not need PassWall2 routing, skip this step. Otherwise open **Basic → Routing** and choose:

- **Main routing profile** — the shunt profile already active in PassWall2.
- **Working VPN connection** — an existing VPN node that already works.

Select **Review selected routing**, inspect the destinations, and then select **Apply recommended routing**. MITM-compatible routes require the service to be running; start it in **Advanced → Service** if necessary. The assistant validates the preview and preserves unrelated PassWall2 rules.

### 4. Check that it works

Open **Basic → Status** and select **Run check**. This verifies the router-side MITM service. It does not prove that every client trusts `mycert.crt`.

After it passes, test the intended websites from a client browser. A site using MITM should show `MITM-DomainFronting` as its certificate issuer; a VPN-routed or direct site should show its normal public certificate authority.

## Recommended routing

The default model is based on traffic purpose:

| Traffic | Destination | Purpose |
| --- | --- | --- |
| Google services | MITM | Use the local MITM service for the selected Google bundle. |
| Gemini app and API | Selected VPN | Send Gemini traffic through the working VPN. |
| Iranian websites and IP addresses | Direct | Avoid the VPN and MITM for selected local traffic. |

Optional service groups are available in **Basic → Routing**:

- **VPN Overrides** can include Android connectivity checks, YouTube sign-in and controls, and Google Account sign-in. `googlevideo.com` is excluded so high-speed YouTube video delivery can use MITM.
- **MITM-Compatible Services** can include Google, Meta, and Fastly-backed website groups. Google is the recommended starting point; test Meta and Fastly before relying on native applications.
- **Regional Direct Access** uses the packaged Iranian domain and IP groups.

Each checkbox enables a service group inside one of these assignments; it does not create a separate rule. Most users can keep the recommended choices unchanged.

## Updating

Run the same installation command again. It preserves the configuration, active certificate, service state, and PassWall2 routing. Reload LuCI and review the status cards; do not generate a new certificate or repeat setup unless LuCI asks you to.

## Common problems

- **PassWall2 is not detected:** MITM can still run, but automatic routing requires PassWall2. Install and enable it, then reload LuCI.
- **No VPN or routing profile:** add and test a VPN node or shunt profile in PassWall2, then return to **Basic → Routing**.
- **MITM routes do not work:** in **Advanced → Service**, confirm that MITM is running and the client trusts `mycert.crt`.
- **Certificate error:** install only the current `mycert.crt`. Never copy `mycert.key`; review certificate state in **Advanced → Certificates**.
- **Native app fails:** some apps ignore user-installed CAs, use certificate pinning, or use traffic outside the selected group. Confirm the browser path first.

## Advanced

Most users do not need the technical reference. It covers certificate lifecycle, manual service controls, custom routing, rollback, recovery, local SOCKS details, and CLI commands:

- [Advanced usage](docs/ADVANCED.md)
- [Security](SECURITY.md)
- [Signed feed operations](docs/SIGNED_FEED.md)
- [Release testing](docs/RELEASE_TESTING.md)
- [Contributing and development workflow](CONTRIBUTING.md)

## Remove

If routing was applied, roll it back in LuCI first. Then stop and remove the packages on the router:

**ROUTER:**

```sh
/etc/init.d/xray-mitm stop
/etc/init.d/xray-mitm disable
apk del luci-app-xray-mitm xray-mitm
```

Remove `mycert.crt` from client trust stores when interception is no longer intended. Treat remaining backups and `mycert.key` as secret material.

## Attribution

The packaged domain-fronting configuration is derived from [patterniha/MITM-DomainFronting v23](https://github.com/patterniha/MITM-DomainFronting/tree/v23), licensed under GPL-3.0. Xray-core, OpenWrt, LuCI, and PassWall2 remain separate upstream projects. See [third-party notices](THIRD_PARTY_NOTICES.md).
