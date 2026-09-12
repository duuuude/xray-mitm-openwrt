#!/usr/bin/env python3
"""Structural tests for the packaged Xray sample configuration."""

from __future__ import annotations

import json
import unittest
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
SAMPLE = PROJECT / "xray-mitm/files/usr/share/xray-mitm/config.json.example"


def walk(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key, child
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


class PackagedConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = json.loads(SAMPLE.read_text(encoding="utf-8"))
        cls.outbounds = {
            item["tag"]: item
            for item in cls.config["outbounds"]
            if isinstance(item, dict) and isinstance(item.get("tag"), str)
        }
        cls.routing_rules = cls.config["routing"]["rules"]
        cls.routing_tags = {
            rule["outboundTag"]
            for rule in cls.routing_rules
            if isinstance(rule, dict) and isinstance(rule.get("outboundTag"), str)
        }

    def test_runtime_json_contains_no_attribution_or_donation_metadata(self) -> None:
        self.assertNotIn("__Credits__", self.config)
        serialized = SAMPLE.read_text(encoding="utf-8").lower()
        self.assertNotIn("donate", serialized)
        self.assertNotIn("patterniha", serialized)

    def test_unneeded_inherited_policies_are_absent(self) -> None:
        serialized = SAMPLE.read_text(encoding="utf-8")
        self.assertNotIn("geosite:category-ads-all", serialized)
        self.assertNotIn("geosite:khanacademy", serialized)
        self.assertNotIn("tls-repack-frommitm", serialized)

    def test_every_packaged_outbound_is_reachable_from_routing(self) -> None:
        self.assertEqual(set(self.outbounds), self.routing_tags)

    def test_retained_aliases_have_the_expected_consumers(self) -> None:
        hosts = self.config["dns"]["hosts"]
        self.assertEqual(hosts["fastly.redirect"], "github.githubassets.com")
        self.assertEqual(hosts["dns.redirect"], ["1.1.1.1", "1.0.0.1"])

        serialized = SAMPLE.read_text(encoding="utf-8")
        self.assertIn('"redirect": "fastly.redirect:443"', serialized)
        self.assertIn('"redirect": "dns.redirect:443"', serialized)

    def test_managed_google_fallbacks_and_localhost_boundaries_remain(self) -> None:
        self.assertEqual(
            {
                (item["tag"], item["listen"], item["port"])
                for item in self.config["inbounds"]
            },
            {
                ("mixed-in", "127.0.0.1", 10808),
                ("tls-decrypt-h11", "127.0.0.1", 11666),
                ("tls-decrypt-h211", "127.0.0.1", 11777),
            },
        )
        serialized = SAMPLE.read_text(encoding="utf-8")
        self.assertIn('"domain:googlevideo.com"', serialized)
        self.assertIn('"geosite:google"', serialized)
        self.assertIn('"geosite:meta"', serialized)
        self.assertIn('"geosite:fastly"', serialized)

    def test_no_private_key_material_is_embedded(self) -> None:
        for key, value in walk(self.config):
            if key == "keyFile":
                self.assertEqual(value, "/etc/xray-mitm/mycert.key")
            if isinstance(value, str):
                self.assertNotIn("BEGIN ", value)
                self.assertNotIn("0x76a768", value)


if __name__ == "__main__":
    unittest.main(verbosity=2)
