---
title: Node versions and memory
date: 2026-06-01
type: measurement
source: raw/2026-06-01-pve-versions.txt
source_hash: 0058373ed1bdf6d3
trust_level: measured
origin: "pveversion; free -m @ pve1, pve2"
redactions: {secret: 0, ip: 0, mac: 0}
---

## Summary

Proxmox version and memory use of both nodes on 2026-06-01 (`pveversion`, `free -m`).

## Key points

- Both nodes run `pve-manager/8.4.1` on kernel `6.8.12-10-pve`.
- pve1: 31958 MiB of RAM, 29870 used, 2088 available; 6210 of 8191 MiB of swap in use.
- pve2: 15894 MiB of RAM, 6124 used, 9770 available; no swap in use.

## Entities mentioned

[[entities/host-pve1]], [[entities/host-pve2]]

## Concepts mentioned

[[concepts/memory-overcommit]]
