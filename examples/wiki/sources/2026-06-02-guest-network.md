---
title: Guest network configuration
date: 2026-06-02
type: measurement
source: raw/2026-06-02-guest-network.txt
source_hash: 58a2c52c099f0bd6
trust_level: measured
origin: "pct config 101, 102 and qm config 200, net0 lines"
redactions: {secret: 0, ip: 0, mac: 0}
---

## Summary

The `net0` lines of the three guests whose addresses matter, 2026-06-02.

## Key points

- CT 101: static `ip=10.0.0.53/24`, gateway `10.0.0.1`, MAC `BC:24:11:00:01:01`.
- CT 102: `ip=dhcp`, MAC `BC:24:11:00:01:02`: its address is not in the container.
- VM 200: `virtio=BC:24:11:00:02:00` and no address: the VM config does not hold one.

## Entities mentioned

[[entities/ct-101-pihole]], [[entities/ct-102-pihole]], [[entities/vm-200-nas]]

## Concepts mentioned

[[concepts/circular-dhcp-reservation]]
