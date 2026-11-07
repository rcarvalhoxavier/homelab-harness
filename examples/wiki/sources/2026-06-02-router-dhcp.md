---
title: Router DHCP reservations and config backup
date: 2026-06-02
type: measurement
source: raw/2026-06-02-router-dhcp.txt
source_hash: 855732f8a61b5716
trust_level: measured
origin: "edge-router UI export: DHCP reservations, config backup settings"
redactions: {secret: 0, ip: 0, mac: 0}
---

## Summary

Export from the edge-router admin interface on 2026-06-02: DHCP reservations, the DNS servers
given to clients, and where the router saves its own configuration.

## Key points

- Reservations: pve1 `10.0.0.11`, pve2 `10.0.0.12`, rpi `10.0.0.20`, nas `10.0.0.30`
  (MAC `bc:24:11:00:02:00`), pihole2 `10.0.0.54` (MAC `bc:24:11:00:01:02`).
- DNS servers given to every client: `10.0.0.53` and `10.0.0.54`.
- Weekly configuration backup to `nfs://10.0.0.30/mnt/tank/router-backups`, which is the NAS.

## Entities mentioned

[[entities/edge-router]], [[entities/vm-200-nas]], [[entities/ct-102-pihole]],
[[entities/host-pve1]], [[entities/host-pve2]], [[entities/host-rpi]], [[entities/pihole]]

## Concepts mentioned

[[concepts/circular-dhcp-reservation]]
