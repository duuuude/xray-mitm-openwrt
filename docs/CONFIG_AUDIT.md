# Packaged Xray configuration audit

This audit covers the new-install sample at
`xray-mitm/files/usr/share/xray-mitm/config.json.example`. It does not replace
an existing `/etc/xray-mitm/config.json`; the installer and the LuCI setup flow
preserve an existing custom configuration.

## Decisions

| Behavior | Decision | Reason |
| --- | --- | --- |
| Creator and donation metadata | Removed from the runtime JSON | It is not Xray configuration. Attribution belongs in [`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md). |
| `remarks` metadata | Removed from the runtime JSON | It has no routing or MITM effect and is not used by this project. |
| `geosite:category-ads-all` block and DNS host | Removed | The project has no ad-blocking control or documented ad-blocking promise. A new installation should not silently add that policy. |
| `tls-repack-frommitm` | Removed | No routing rule referenced this outbound, so it could never be selected. |
| `fastly.redirect` | Retained | `tls-repack-fastly` uses it to send the optional Fastly-backed bundle to the fronting address. |
| `dns.redirect` | Retained | `tls-repack-dns` uses it for the no-filter DNS path. |
| FakeDNS, private, and regional DNS handling | Retained | These support domain resolution for localhost MITM routing and the regional direct route. |
| Localhost listeners and certificate paths | Retained | PassWall2 uses the localhost SOCKS listener, and the decrypt listeners require the managed public certificate and private key pair. |
| Google video, Drive/API, and Meet repack paths | Retained | These are the supported Google MITM service bundles. Meet media limitations remain documented in the user guides. |
| Broad internal `geosite:google` match | Retained as a fallback | Supported PassWall2 routing selects explicit Drive, `googlevideo.com`, and Meet hostnames. The broader internal match is useful for compatible custom local-SOCKS traffic and does not cause ordinary client traffic to enter MITM by itself. |
| Broad Meta and Fastly matches | Retained | These match the optional MITM service bundles exposed by PassWall2. |
| `geosite:khanacademy` direct exception | Removed | It was an inherited exception outside the supported service groups and regional direct-access definition. |
| Hard-coded blocked IP ranges | Retained | They are an upstream safety fallback used by the packaged policy; removing them without identifying the ranges in a live service test would weaken behavior without a product benefit. |

## Request path

For supported PassWall2 use, the path is:

```text
client
→ PassWall2 service-group selection
→ local MITM SOCKS at 127.0.0.1:10808
→ Xray internal routing and TLS repack
```

The PassWall2 helper supplies explicit domains for the managed Google and Meet
bundles. Xray's broader internal rules are therefore a fallback for traffic
that has already entered the localhost MITM path; they do not change the
PassWall2 assignment of ordinary Google traffic. Google Play, Android
services, account sign-in, and YouTube controls remain separate VPN overrides.

## Validation

The offline release validator checks the sample JSON, fixed localhost
listeners, managed certificate paths, and the required geo assets. The config
audit test also checks that removed metadata and policies do not return, that
every packaged outbound is referenced by routing, and that each retained
alias has a consumer.

The exact candidate should still be validated on the AX4200 with:

**MAC:**

```sh
sh scripts/router-local-test.sh config-validate
```

This copies the sample to a temporary router directory, runs Xray's
configuration test with the router's configured asset directory, and removes
the temporary file. It does not replace `/etc/xray-mitm/config.json`, restart
Xray, or apply PassWall2 routing.

For a direct read-only command on the router, use:

**ROUTER:**

```sh
XRAY_LOCATION_ASSET=/usr/share/v2ray xray run -test -format=json -c /etc/xray-mitm/config.json
```

Use the service's configured asset directory when running the command. A
one-shot invocation without it can make Xray search `/usr/bin` for `geoip.dat`
and report a false configuration failure.
