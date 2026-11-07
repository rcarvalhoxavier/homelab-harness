---
title: Simulations before the Pi-hole v6 upgrade
date: 2026-06-14
type: measurement
source: raw/2026-06-14-pihole-simulation.txt
source_hash: ee5f034c07f4bc47
trust_level: measured
origin: pihole -up --check-only; apt-get -s dist-upgrade @ ct-101
redactions: {secret: 0, ip: 0, mac: 0}
---

## Summary

The simulations run on CT 101 before [[changes/2026-06-14-pihole-v6-upgrade]].

## Key points

- `pihole -up --check-only`: updates available for Core, the web interface and FTL.
- `apt-get -s dist-upgrade`: 3 packages upgraded (`curl`, `libcurl4`, `openssl`), 0 newly
  installed, 0 to remove.

## Entities mentioned

[[entities/ct-101-pihole]]

## Concepts mentioned

[[concepts/simulate-before-irreversible]]
