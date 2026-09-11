# Xray MITM Domain Fronting for OpenWrt

**Instructions:** English | [فارسی](README.fa.md)

**Project:** [Changelog](CHANGELOG.md) | [Contributing](CONTRIBUTING.md)

This project packages a standalone Xray MITM-DomainFronting service, a LuCI management page, and optional PassWall2 routing for official OpenWrt 25.12 APK-based routers.

> [!CAUTION]
> A trusted MITM certificate authority can decrypt HTTPS traffic from devices that trust it. Use it only on networks and devices you own or are authorized to manage. Install only `mycert.crt` on clients. Keep `mycert.key` on the router and in protected backups.

## Start here

The supported public feed currently targets official OpenWrt **25.12.5 and later 25.12 maintenance releases**. The router must use the `apk` package manager and have internet access to GitHub and GitHub Pages.

### 1. Install or update with one command

Replace `192.168.1.1` if your router uses another address. Enter the router password when asked.

**MAC:**

```sh
ssh root@192.168.1.1 'wget -qO /tmp/install-xray-mitm.sh https://duuuude.github.io/xray-mitm-openwrt/install.sh && printf "%s  %s\n" "8af96edc133c01a7e9d0a8f4673b7225c47322d73874c05a9c4a0133f3058405" "/tmp/install-xray-mitm.sh" | sha256sum -c - && sh /tmp/install-xray-mitm.sh'
```

**WINDOWS PC (PowerShell):**

```powershell
ssh.exe root@192.168.1.1 'wget -qO /tmp/install-xray-mitm.sh https://duuuude.github.io/xray-mitm-openwrt/install.sh && printf "%s  %s\n" "8af96edc133c01a7e9d0a8f4673b7225c47322d73874c05a9c4a0133f3058405" "/tmp/install-xray-mitm.sh" | sha256sum -c - && sh /tmp/install-xray-mitm.sh'
```

If you are already connected through SSH:

**ROUTER:**

```sh
wget -qO /tmp/install-xray-mitm.sh https://duuuude.github.io/xray-mitm-openwrt/install.sh && printf '%s  %s\n' '8af96edc133c01a7e9d0a8f4673b7225c47322d73874c05a9c4a0133f3058405' '/tmp/install-xray-mitm.sh' | sha256sum -c - && sh /tmp/install-xray-mitm.sh
```

The command verifies the public installer before running it. Its pinned SHA-256 is `8af96edc133c01a7e9d0a8f4673b7225c47322d73874c05a9c4a0133f3058405`.

The same command handles first installation and later updates. It:

1. Checks the OpenWrt release and package manager.
2. Downloads the project feed public key over HTTPS.
3. Requires this exact SHA-256 fingerprint before trusting the key:

   ```text
   3e0dc07ffef69d1512500b6add486381d8c261a8ec3fcce54fa403b35320df8a
   ```

4. Adds the signed feed to APK and preserves the feed configuration across firmware upgrades.
5. Makes a protected backup under `/root/`.
6. Lets APK verify and install or update `xray-mitm` and `luci-app-xray-mitm` by package name.

The installer never uses `--allow-untrusted`, never upgrades every package on the router, and does not create a CA, start the service, or change PassWall2 routing.

### 2. Complete first-time setup in LuCI

Open LuCI over **HTTPS**, then go to **Services → MITM Domain Fronting**.

This section is for a new installation. If you are updating an existing
installation, skip it: updates preserve the configuration, active CA, service
state, and PassWall2 routing. The setup guide will show **System overview**
and only ask you to complete items that are not ready.

For the beginner path, stay in **Simple** view and select **Set up
automatically**. It installs the packaged configuration when needed,
generates and activates a CA when needed, starts MITM, and enables automatic
startup. It does not replace an existing valid configuration or CA.

After automatic setup:

1. Download only `mycert.crt`.
2. Install `mycert.crt` as a trusted root on each client that should use MITM.
3. Run the health check and confirm it passes.
4. Continue to PassWall2 routing below if you need selective routing.

If you choose **Advanced settings** instead, the equivalent manual sequence
is: install the packaged default configuration, generate or import a matching
certificate and private key as a candidate, activate the candidate, start the
service, run the health check, and enable automatic startup. Never copy
`mycert.key` to a client.

Trust the downloaded public CA for your current user:

**MAC:**

```sh
security add-trusted-cert -r trustRoot \
  -k "$HOME/Library/Keychains/login.keychain-db" ./mycert.crt
```

**WINDOWS PC (PowerShell):**

```powershell
certutil.exe -user -addstore -f Root .\mycert.crt
```

Firefox may use its own certificate store. If it does, import `mycert.crt` inside Firefox too. Never copy `mycert.key` to a client.

### 3. Route selected domains through PassWall2

Skip this step if you only need the local SOCKS service.

1. Open the PassWall2 section on the project’s LuCI page.
2. Choose the existing shunt node and VPN node.
3. If you select any MITM-compatible service, confirm that the MITM service
   is running. The assistant will not allow a preview that would send traffic
   to a stopped local SOCKS listener.
4. Select **Review selected routing** or **Preview changes**.
5. Review the local node, domains, destinations, and rule order.
6. Select **Apply preview** only after the preview is correct.

The assistant creates at most three package-managed rules, in this order:

1. **VPN Overrides** sends selected Gemini, Android connectivity, YouTube control, and Google Account bundles to the chosen VPN. YouTube video delivery (`googlevideo.com`) is deliberately excluded.
2. **MITM-Compatible Services** sends selected Google, Meta website, and Fastly-backed website bundles to the local SOCKS node at `127.0.0.1:10808`. Google is recommended; Meta and Fastly stay off until you test them on your devices.
3. **Regional Direct Access** sends Iranian domains and IP ranges directly.

The checkboxes add domain bundles to these three rules; they do not create one rule per checkbox. Applying the first three-rule preview migrates older package-managed rules. Recognized user-created legacy rules remain unchanged, but their assignments are removed from the selected shunt to prevent duplicate matches. Keep `localhost_proxy=0` to prevent the standalone Xray output from looping back into PassWall2.

### 4. Verify from a client

**MAC:**

```sh
for url in \
  https://www.google.com \
  https://www.youtube.com \
  https://www.cloudflare.com \
  https://gemini.google.com
do
  printf '\n%s\n' "$url"
  curl -Iv --max-time 20 "$url" 2>&1 |
    grep -E 'issuer:|^HTTP/'
done
```

**WINDOWS PC (PowerShell):**

```powershell
$urls = @(
  'https://www.google.com',
  'https://www.youtube.com',
  'https://www.cloudflare.com',
  'https://gemini.google.com'
)

foreach ($url in $urls) {
  Write-Host "`n$url"
  curl.exe -Iv --max-time 20 $url 2>&1 |
    Select-String -Pattern 'issuer:', 'HTTP/'
}
```

A domain using MITM should show:

```text
issuer: CN=MITM-DomainFronting
```

A domain using VPN or direct routing should show its normal public certificate authority. All expected requests should return a successful HTTP response.

## Updating later

The easiest update is to run the same one-command installer again. After the feed is configured, you can also update directly:

**ROUTER:**

```sh
apk update
apk upgrade xray-mitm luci-app-xray-mitm
```

This upgrades only these two explicitly selected packages and required dependencies. Do not use an unrestricted `apk upgrade` as a replacement for a planned OpenWrt firmware upgrade.

Updates preserve `/etc/config/xray-mitm`, `/etc/xray-mitm/`, the active CA, service settings, and existing PassWall2 configuration. The installer creates `/root/xray-mitm-before-install-YYYYMMDD-HHMMSS.tar.gz` with mode `0600` before changing feed or package state.

After an update, reload LuCI and review the status cards. Do not generate a
new CA or run first-time setup again unless the page reports that configuration
or certificate state is missing or needs attention.

## How authentication works

The first one-command run downloads the installer from GitHub over HTTPS. That installer pins the reviewed feed public-key fingerprint shown above. APK then uses the installed public key to authenticate the feed index and every package. Later updates use the same stored key and signed feed.

Production publishing is separate from ordinary pull-request builds:

- Pull requests run offline validation and development artifacts without the production signing key or secrets.
- A version tag must match the package version exactly.
- The signing job runs only behind the protected `signed-feed` GitHub environment.
- The job proves that the protected private key matches the public key committed in `keys/xray-mitm-feed-v1.pem`.
- OpenWrt’s SDK creates the native signed `packages.adb` index and signed APKs.
- The workflow publishes the feed through GitHub Pages and keeps the signed files with the matching GitHub Release.

The production private key is never stored in this repository or included in packages. See [Signed feed operations](docs/SIGNED_FEED.md) for publishing, recovery, and key-rotation procedures.

## Requirements and package behavior

The packages are architecture-independent (`all`) but currently require the official OpenWrt 25.12 APK package ecosystem. Dependencies include `xray-core`, `curl`, `openssl-util`, `uci`, `jsonfilter`, `coreutils-stat`, `v2ray-geoip`, and `v2ray-geosite`; LuCI also requires `luci-base`, `rpcd-mod-ucode`, and `ucode-mod-fs`.

The default installation is intentionally inactive. Installing or updating packages does not generate a CA, enable boot startup, start Xray, alter firewall or DNS state, or apply PassWall2 changes. The three Xray listeners remain on localhost:

| Purpose | Address |
| --- | --- |
| Local mixed/SOCKS entry | `127.0.0.1:10808` |
| HTTP/1.1 TLS decrypt tunnel | `127.0.0.1:11666` |
| HTTP/2 TLS decrypt tunnel | `127.0.0.1:11777` |

## Manual authenticated installation

Use this only when the router cannot reach GitHub Pages. Download the two APKs, `xray-mitm-feed-v1.pem`, `PUBLIC_KEY_SHA256`, and `SHA256SUMS` from the same signed GitHub Release on a Mac or Windows PC.

**ROUTER:**

```sh
mkdir -p -m 0700 /tmp/xray-mitm-install
```

**MAC:**

```sh
cd "/path/to/downloaded/release-files"
scp -O xray-mitm-*.apk luci-app-xray-mitm-*.apk \
  xray-mitm-feed-v1.pem PUBLIC_KEY_SHA256 SHA256SUMS \
  root@192.168.1.1:/tmp/xray-mitm-install/
```

**WINDOWS PC (PowerShell):**

```powershell
Set-Location "C:\path\to\downloaded\release-files"
scp.exe -O .\xray-mitm-*.apk .\luci-app-xray-mitm-*.apk `
  .\xray-mitm-feed-v1.pem .\PUBLIC_KEY_SHA256 .\SHA256SUMS `
  root@192.168.1.1:/tmp/xray-mitm-install/
```

Verify the public-key fingerprint before installing it. Stop if it differs from the fingerprint in this README.

**ROUTER:**

```sh
cd /tmp/xray-mitm-install
printf '%s  %s\n' \
  '3e0dc07ffef69d1512500b6add486381d8c261a8ec3fcce54fa403b35320df8a' \
  'xray-mitm-feed-v1.pem' | sha256sum -c -
awk '$2 ~ /[.]apk$/' SHA256SUMS | sha256sum -c -
mkdir -p /etc/apk/keys
cp xray-mitm-feed-v1.pem /etc/apk/keys/xray-mitm-feed-v1.pem
chmod 0644 /etc/apk/keys/xray-mitm-feed-v1.pem
apk add ./xray-mitm-*.apk ./luci-app-xray-mitm-*.apk
```

CI development APKs are intentionally outside this production trust path. Do not present them to new users as signed releases.

## Development and release testing

See [Contributing](CONTRIBUTING.md) for the local branch and pull request workflow,
and [Changelog](CHANGELOG.md) for user-facing release history.

Run all offline safety, installer, routing, certificate, workflow, and syntax checks:

**MAC:**

```sh
cd "/path/to/xray-mitm-openwrt"
sh scripts/validate-release.sh
```

**WINDOWS PC (PowerShell with WSL):**

```powershell
wsl.exe sh -lc 'cd /path/to/xray-mitm-openwrt && sh scripts/validate-release.sh'
```

See [Release testing](docs/RELEASE_TESTING.md) before publishing a tag.

## Removal

Before removing the packages, stop the service, disable boot startup, and use the LuCI PassWall2 rollback if routing was applied. Then remove the packages:

**ROUTER:**

```sh
/etc/init.d/xray-mitm stop
/etc/init.d/xray-mitm disable
apk del luci-app-xray-mitm xray-mitm
```

Remove `mycert.crt` from every client trust store when interception is no longer intended. Treat any remaining router backup and `mycert.key` as secret material.

## Attribution

The domain-fronting configuration is derived from [patterniha/MITM-DomainFronting v23](https://github.com/patterniha/MITM-DomainFronting/tree/v23), licensed under GPL-3.0. Xray-core, OpenWrt, LuCI, and PassWall2 remain separate upstream projects. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
