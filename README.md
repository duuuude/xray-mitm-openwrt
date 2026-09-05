# Xray MITM Domain Fronting for OpenWrt

This repository packages a standalone Xray MITM-DomainFronting service and a small LuCI management page for OpenWrt. It is designed for official OpenWrt **25.12.5 and later APK-based releases**, subject to a build and lab test for each release, and is not tied to the ASUS TUF-AX4200 or to the `mediatek/filogic` target.

> [!CAUTION]
> A locally trusted MITM certificate authority can decrypt traffic from devices that trust it. Use this only on networks and devices you own or are explicitly authorized to administer. Never publish, email, or otherwise share the generated CA private key.

## Package architecture

| Package | Responsibility | Architecture |
| --- | --- | --- |
| `xray-mitm` | UCI defaults, procd service, hardened sample configuration, certificate lifecycle, health check, and optional PassWall2 helper | `all` (noarch) |
| `luci-app-xray-mitm` | LuCI page and narrow rpcd interface for status, service control, public-certificate export, staged certificate setup, and routing preview | `all` (noarch) |

The project does **not** bundle an Xray executable. APK resolves the official `xray-core` package for the router's CPU architecture. This keeps the project model-independent while letting OpenWrt supply and update the native executable.

An architecture-independent package is not automatically compatible with every OpenWrt fork or release. Build against the OpenWrt release used by the router, and confirm that its repositories provide a compatible `xray-core`. The current configuration requires Xray 26.2.6 or newer.

## Requirements and dependencies

The intended build baseline is official OpenWrt 25.12.5 with APK and enough storage and memory for Xray. APK installation and runtime behavior still require lab-router validation. A later release is supported only after its official feeds provide all named dependencies and its SDK build and lab-router checks pass. The package metadata is authoritative; the intended direct dependencies are:

- Core: `xray-core`, `curl`, `openssl-util`, `uci`, `jsonfilter`, `coreutils-stat`,
  `v2ray-geoip`, and `v2ray-geosite`.
- LuCI: `luci-base`, `xray-mitm`, `rpcd-mod-ucode`, and `ucode-mod-fs`.
- `ca-bundle` is supplied by the normal OpenWrt/Xray dependency chain.
- `v2ray-geoip` and `v2ray-geosite` provide the `geoip.dat` and
  `geosite.dat` assets referenced by the packaged configuration.

PassWall2 is optional and deliberately is not a hard package dependency. It is third-party software whose UCI schema can vary across versions and forks. `sing-box`, `dnsmasq-full`, firewall modules, and transparent-proxy kernel modules are also not dependencies of the standalone service.

## Safe first run

Installation leaves the service disabled and unprovisioned. It does not generate a CA, import a key, start Xray, or modify PassWall2, firewall, DNS, or routing state.

After installation:

1. Open LuCI over **HTTPS**, then go to **Services → MITM Domain Fronting**.
2. Select **Install packaged default configuration** for a fresh installation. Existing configurations are preserved; the installer refuses to overwrite them.
3. Generate a staged CA on the router, or import a matching certificate and private-key pair that you already control. Private-key import should never be performed over plain HTTP.
4. Download only the public certificate and install it as a trusted root on the client devices that need this service.
5. Activate the staged pair, select **Start**, and run the health check. Select **Enable at boot** if automatic startup is wanted.
6. Preview the optional PassWall2 integration. Apply it only after reviewing the proposed node, rules, targets, and order.

The private key is stored on the router with mode `0600`, meaning only `root` can read or change it. LuCI never offers a private-key download. The public certificate may be downloaded and distributed to trusted clients; it cannot be used to impersonate sites without the private key.

OpenWrt configuration backups made after provisioning may contain the CA private key. After the optional PassWall2 integration is applied, the root-only rollback snapshot also contains the complete prior PassWall2 configuration and may therefore contain node credentials. Treat these files and every sysupgrade backup containing them as secret material; never attach them to a GitHub issue or release.

## Optional PassWall2 routing

The integration helper is intentionally opt-in. It must detect the installed PassWall2 schema, show a preview, create a rollback snapshot, and stop without making changes if compatibility cannot be established. A typical policy is:

1. `Gemini_VPN` → the selected VPN node.
2. `Android_Check` → VPN, if Android connectivity checks need it.
3. `YouTube_Control_VPN` → VPN for selected control/account API hostnames only, if needed.
4. `Google_MITM` → local SOCKS node `127.0.0.1:10808`.
5. `IR_Direct` → direct, using `geosite:ir` and `geoip:ir` when those datasets are installed.

Rule order matters: higher entries on PassWall2's Rule Manage page have higher priority. Do not put `googlevideo.com` in the YouTube VPN control rule if video delivery is intended to use the faster MITM path. The preview selects `localhost_proxy=0` by default to prevent the standalone Xray outbound from being captured again; it is still shown as a separate opt-in transaction change before anything is applied.

QUIC/HTTP/3 is not intercepted like TCP/TLS. A separate LAN UDP/443 rejection rule can force clients to fall back to TCP, but this package does not create that broad firewall rule automatically. Certificate-pinned native applications may still reject interception even when browsers work.

An interrupted routing transaction is restored automatically before a new preview, apply, or rollback. When the xray-mitm boot service is enabled, it also attempts this recovery at priority 98, before the commonly used PassWall2 priority 99. If recovery is still pending, LuCI shows an explicit recovery action and will not present the in-flight configuration as safe to edit.

## Build with GitHub Actions

The checked-in workflow validates the release tree, then builds both noarch APKs with the official OpenWrt SDK action. Its default is the OpenWrt 25.12.5 `aarch64_generic` SDK; a manual run can select another official SDK architecture or later OpenWrt release. Because both packages declare `all`, the output APKs contain no target-native program.

From GitHub, open **Actions → Build OpenWrt APKs → Run workflow**. Set the SDK architecture and release to match a supported official SDK container. The result contains both APKs, `SHA256SUMS`, the license and attribution files, and `SOURCE_COMMIT` identifying the exact source revision. CI artifacts are development packages and are not signed by a key trusted by a stock router; verify their checksums and use `--allow-untrusted` only when you trust the repository and workflow run.

Tag pushes run the same read-only build but deliberately do not create a GitHub Release. After the APKs pass the lab-router checklist, create the Release manually and attach the validated artifact files. This keeps pull-request builds and release publishing under separate permissions.

To validate the source locally without a router:

**MAC:**

```sh
cd "/path/to/xray-mitm-openwrt"
sh scripts/validate-release.sh
```

## Build manually with an OpenWrt SDK

The SDK tools are Linux binaries. On macOS, run these commands inside a Linux VM or container using a fresh SDK for the router's OpenWrt release.

**MAC (inside the Linux build environment):**

```sh
sdk_dir="/path/to/openwrt-sdk-25.12.5"
source_dir="/path/to/xray-mitm-openwrt"
cd "$sdk_dir"
printf 'src-link xray_mitm %s\n' "$source_dir" >> feeds.conf
./scripts/feeds update -a
./scripts/feeds install -p xray_mitm -f xray-mitm luci-app-xray-mitm
make defconfig
make package/feeds/xray_mitm/xray-mitm/compile V=s
make package/feeds/xray_mitm/luci-app-xray-mitm/compile V=s
find bin/packages -type f -name '*xray-mitm*.apk' -print
```

Use a fresh SDK or remove an old `src-link xray_mitm` entry before repeating the setup, so `feeds.conf` does not accumulate duplicates.

## Install the APKs

First confirm the router really uses APK and meets the release baseline. Do not substitute OPKG commands from older firmware.

**ROUTER:**

```sh
. /etc/openwrt_release
printf 'OpenWrt release: %s\n' "$DISTRIB_RELEASE"
apk --version
```

Copy the two APKs and checksum file. OpenWrt's Dropbear setup often lacks an SFTP server, so modern macOS `scp` may require legacy protocol mode:

**ROUTER:**

```sh
mkdir -p -m 0700 /tmp/xray-mitm-install
```

**MAC:**

```sh
scp -O dist/xray-mitm-*.apk dist/luci-app-xray-mitm-*.apk dist/SHA256SUMS root@192.168.1.1:/tmp/xray-mitm-install/
```

Verify before installing, then let APK resolve the native `xray-core` and other dependencies from the configured OpenWrt feeds.

**ROUTER:**

```sh
cd /tmp/xray-mitm-install
sha256sum -c SHA256SUMS
apk update
apk add --allow-untrusted ./xray-mitm-*.apk ./luci-app-xray-mitm-*.apk
```

`--allow-untrusted` is needed when the router does not trust the build's package-signing key; it is not a replacement for checksum verification or for reviewing the source. A future package feed signed with a deliberately managed, published key should be preferred for public releases.

## Upgrade and removal behavior

Package upgrades preserve `/etc/config/xray-mitm` and the complete `/etc/xray-mitm/` directory. A newer packaged sample is placed under `/usr/share/xray-mitm/`; it never silently overwrites an active configuration, CA, private key, or routing snapshot.

Before uninstalling, stop the service, disable automatic start, and use the LuCI PassWall2 rollback while the latest transaction is still eligible. Removing the APKs does not silently remove PassWall2 rules, revoke client trust, or erase preserved configuration and CA material. Otherwise a stale routing rule could continue sending selected traffic to a listener that no longer exists. Remove the public CA from every client trust store when interception is no longer intended, and handle any remaining router-side private key as secret material.

## Release safety

The release validator rejects common router backups, package inventories, generated APKs, CA material, and PEM private-key content. Before publishing, review the complete Git diff as well. In particular, never commit:

- `/etc/xray-mitm/mycert.key` or any other private key.
- A generated `mycert.crt`; each installation should use its own CA.
- `sysupgrade -b` archives, `/etc/shadow`, Dropbear host keys, or uhttpd private keys.
- Live PassWall2 configuration, VPN subscription data, node credentials, or router package inventories.

## Attribution

The domain-fronting configuration is derived from [patterniha/MITM-DomainFronting v23](https://github.com/patterniha/MITM-DomainFronting/tree/v23), licensed under GPL-3.0. Local changes bind listeners to localhost, use explicit OpenWrt paths, and add service, certificate, health-check, LuCI, and optional PassWall2 management. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Xray-core, OpenWrt, LuCI, and PassWall2 remain separate upstream projects. They are not bundled here, and this repository is not an official release of any of them.
