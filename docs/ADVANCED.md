# Advanced usage

Most users should follow the main [README](../README.md). This page documents the controls and implementation details that are useful when the Basic dashboard needs more information.

## Dashboard modes

The LuCI page uses one client-side view with two modes:

- **Basic** — setup, certificate download, recommended routing, and status.
- **Advanced** — **Overview**, **Service**, **Certificates**, and **Routing** pages for manual control.

Switching pages does not reload the LuCI view.

## Service and local listeners

Installing or updating packages does not start the service. The Advanced **Service** page can install the packaged default configuration, start or stop the service, enable or disable automatic startup, and run the MITM health check.

The service is designed to keep its listeners on localhost:

| Purpose | Address |
| --- | --- |
| Local mixed/SOCKS entry | `127.0.0.1:10808` |
| HTTP/1.1 TLS decrypt tunnel | `127.0.0.1:11666` |
| HTTP/2 TLS decrypt tunnel | `127.0.0.1:11777` |

The local SOCKS listener is for the PassWall2 MITM-compatible route. It should not be exposed to the LAN or Internet.

## Certificate lifecycle

The **Certificates** page can show three certificate states:

- **Current** — the active certificate and matching private key used by the service.
- **Candidate** — a new certificate pair prepared but not yet active.
- **Previous** — the prior active pair kept for rollback when available.

The application validates certificate and key matching before activation. A candidate is not the same as the current certificate. Clients must trust the public certificate that matches the current active pair.

Only export the public certificate. The private key must remain root-owned with restrictive permissions on the router and in protected backups.

## PassWall2 routing model

The Routing page uses three package-managed rules. Their user-facing names and destinations are:

1. **VPN Overrides** — sends selected Gemini, Android connectivity, YouTube control, Google Play/Android, and Google Account bundles to the chosen VPN.
2. **MITM-Compatible Services** — sends selected Drive and YouTube-video, Meta, and Fastly-backed website bundles to the local SOCKS node at `127.0.0.1:10808`.
3. **Regional Direct Access** — sends selected Iranian domains and IP ranges directly.

The available service groups currently map as follows:

| Group | Entries |
| --- | --- |
| Gemini app and API | `gemini.google.com`, `generativelanguage.googleapis.com` |
| Android internet checks | `connectivitycheck.gstatic.com`, `connectivitycheck.android.com`, `clients3.google.com` |
| YouTube sign-in and controls | `www.youtube.com`, `youtubei.googleapis.com`, `youtube.googleapis.com`, `accounts.youtube.com` |
| Google Play and Android services | Play, Android authentication, check-in, and download endpoints |
| Google Account sign-in | `accounts.google.com` |
| Google Drive and YouTube video | `drive.google.com`, `drive.usercontent.google.com`, `www.googleapis.com`, `content.googleapis.com`, `googlevideo.com` |
| Google Meet web and signaling | `meet.google.com`, `meetings.googleapis.com`, `hangouts.googleapis.com`, `meetings.clients6.google.com`, `stream.meet.google.com` |
| Meta websites | `geosite:meta` |
| Fastly-backed websites | `geosite:fastly`, `geosite:reddit`, `geosite:cnn`, `buzzfeed.com` |
| Iranian websites and IP addresses | `geosite:ir`, `geoip:ir` |

The Google MITM bundle uses only the explicit Drive, Google API, and `googlevideo.com` domains above. Google Play, Android services, account sign-in, and YouTube controls remain separate VPN overrides so they do not enter the MITM path.

The checkboxes select entries inside these assignments. They do not create one PassWall2 rule per checkbox. The assistant creates or reuses the local SOCKS node when needed, previews the exact change, and applies it only after the reviewed preview is accepted.

The first three-rule apply can migrate older package-managed rules. It preserves unrelated user-created rules while removing their selected-shunt assignments when necessary to avoid duplicate matches. The advanced option `localhost_proxy=0` prevents the local MITM connection from being captured again.

## Preview, apply, rollback, and recovery

The routing assistant requires a compatible PassWall2 installation, a selected shunt, a working VPN node, and a writable configuration. It refuses a MITM-dependent apply while the MITM service is stopped.

The assistant creates a private temporary preview first. Applying is limited to that exact preview, and a rollback copy is kept. If an interrupted transaction is reported, use **Recover previous PassWall2 file** before creating another preview.

Pending PassWall2 changes must be saved or reverted before a new preview can be created.

## CLI reference

These commands run on the router. Most return JSON; certificate export returns the public certificate.

**ROUTER:**

```sh
xray-mitmctl status-json
xray-mitmctl setup-status-json
xray-mitmctl setup-recommended
xray-mitmctl health-json
xray-mitmctl service start
xray-mitmctl service stop
xray-mitmctl service enable
xray-mitmctl service disable
xray-mitmctl config-install-default
xray-mitmctl cert-status-json
xray-mitmctl cert-export current
xray-mitmctl passwall2 inspect
xray-mitmctl passwall2 recover
```

Certificate generation, import, activation, discard, and rollback require the exact fingerprint arguments shown by the certificate status and are safer through the Advanced page.

## Manual authenticated package installation

Use this only when the router cannot reach GitHub Pages. Download both APKs and the matching `xray-mitm-feed-v1.pem`, `PUBLIC_KEY_SHA256`, and `SHA256SUMS` from one signed GitHub Release. Verify the public-key fingerprint and package checksums before installing.

The current feed-key SHA-256 is documented in [Security](../SECURITY.md). Never use `--allow-untrusted` and never mix APKs from different releases.

## Removal

If PassWall2 routing was applied, roll it back first. On the router, stop and disable the service before removing both packages:

**ROUTER:**

```sh
/etc/init.d/xray-mitm stop
/etc/init.d/xray-mitm disable
apk del luci-app-xray-mitm xray-mitm
```
