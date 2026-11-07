---
title: Pi-hole on CT 101 before the v6 upgrade
date: 2026-06-14
type: measurement
source: raw/2026-06-14-pihole-baseline.txt
source_hash: af8c63a92a5bb0b5
trust_level: measured
origin: collector pihole-state @ ct-101 (pct listsnapshot on pve1)
redactions: {secret: 0, ip: 0, mac: 0}
---

## Summary

The baseline of [[changes/2026-06-14-pihole-v6-upgrade]]: collector `pihole-state` on CT 101
before the upgrade.

## Key points

- Core `v5.18.4`, Web `v5.21`, FTL `v5.25.2`; latest available: `v6.1.2`, `v6.2.1`, `v6.1`.
- FTL listening on port 53 (UDP and TCP); blocking enabled.
- `nas.lab.example` resolves to `10.0.0.30`.
- No snapshot of CT 101.

## Entities mentioned

[[entities/ct-101-pihole]], [[entities/pihole]]

## Concepts mentioned

None.
