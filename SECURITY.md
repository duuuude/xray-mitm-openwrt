# Security

This project combines HTTPS interception with optional PassWall2 routing. Read this page before installing it.

## MITM trust boundary

A device that trusts the project CA can have HTTPS traffic decrypted for domains sent through the MITM service. Use the software only on networks and devices you own or are authorized to manage.

- Install only the public certificate, `mycert.crt`, on clients.
- Keep `mycert.key` on the router and in protected backups.
- Do not place the private key in Git, release assets, screenshots, support messages, or terminal transcripts.
- The service listeners are intended to remain on `127.0.0.1`.
- Remove the public certificate from clients when interception is no longer intended.

Some applications ignore user-installed CAs or use certificate pinning. A successful router health check does not prove that every application or client will accept the certificate.

## Signed package feed

The installer and package feed use separate checks:

```text
download installer over HTTPS
→ verify the pinned installer SHA-256
→ download the feed public key
→ verify the feed key fingerprint
→ let APK verify the signed package index and packages
```

The current public feed key is:

```text
File: keys/xray-mitm-feed-v1.pem
SHA-256: 3e0dc07ffef69d1512500b6add486381d8c261a8ec3fcce54fa403b35320df8a
```

The installer does not use `--allow-untrusted` and does not run an unrestricted system-wide package upgrade. It targets `xray-mitm` and `luci-app-xray-mitm` and keeps a protected backup before changing feed state.

## Production signing boundary

Pull-request builds are development artifacts. They do not receive the production signing private key. Production feed signing runs only through the protected GitHub environment `signed-feed`.

The publishing workflow checks that the protected private key derives the same public key as the committed `keys/xray-mitm-feed-v1.pem`. The private key is never stored in this repository, package files, workflow artifacts, release assets, router images, or commands.

For key storage, publishing, recovery, and rotation procedures, see [Signed feed operations](docs/SIGNED_FEED.md).

## Reporting a security issue

Do not post private keys, router backups, credentials, or sensitive router configuration in a public issue. Use the repository's private GitHub security reporting channel when available, or contact the maintainer privately with the minimum reproducible information.

