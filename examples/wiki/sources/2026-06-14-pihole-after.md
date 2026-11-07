---
title: Pi-hole on CT 101 after the v6 upgrade
date: 2026-06-14
type: measurement
source: raw/2026-06-14-pihole-after.txt
source_hash: 485d28bb896dbd02
trust_level: measured
origin: collector pihole-state @ ct-101 (pct listsnapshot on pve1)
redactions: {secret: 0, ip: 0, mac: 0}
---

## Summary

The after-capture of [[changes/2026-06-14-pihole-v6-upgrade]]: the same collector on CT 101,
after the upgrade.

## Key points

- Core `v6.1.2`, Web `v6.2.1`, FTL `v6.1`: all at the latest version.
- FTL still listening on port 53 (UDP and TCP); blocking still enabled.
- `nas.lab.example` still resolves to `10.0.0.30`.
- Snapshot `pre-pihole-v6`, taken 2026-06-14 20:05:31, "before the v6 upgrade".

## Entities mentioned

[[entities/ct-101-pihole]], [[entities/pihole]], [[entities/storage-local-lvm]]

## Concepts mentioned

[[concepts/snapshot-depends-on-storage]], [[concepts/reversibility-by-infrastructure]]
