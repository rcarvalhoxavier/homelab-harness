---
title: "Pi-hole pair: query share and local records"
date: 2026-06-20
type: measurement
source: raw/2026-06-20-pihole-pair.txt
source_hash: e32822bce4af08e5
trust_level: measured
origin: "pihole-FTL query counts (7 days) and local DNS records @ ct-101, ct-102"
redactions: {secret: 0, ip: 0, mac: 0}
---

## Summary

One week of query counts (2026-06-13 to 2026-06-20) and the local DNS records of both Pi-hole
instances.

## Key points

- CT 101 answered 412381 queries and CT 102 38907: about 91 % and 9 % of 451288.
- CT 101 holds 14 local records, CT 102 holds 11.
- Missing on CT 102: `nas.lab.example`, `rpi.lab.example`, `backup.lab.example`.

## Entities mentioned

[[entities/ct-101-pihole]], [[entities/ct-102-pihole]], [[entities/pihole]]

## Concepts mentioned

None. Analysis: [[analyses/2026-06-20-pihole-pair-redundancy]]
