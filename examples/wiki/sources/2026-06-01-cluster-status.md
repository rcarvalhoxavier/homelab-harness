---
title: Cluster quorum status
date: 2026-06-01
type: measurement
source: raw/2026-06-01-cluster-status.txt
source_hash: 52652c47f4454bea
trust_level: measured
origin: pvecm status @ pve1
redactions: {secret: 0, ip: 0, mac: 0}
---

## Summary

Quorum state of the cluster `lab` as seen from pve1 on 2026-06-01 (`pvecm status`).

## Key points

- Two nodes, one vote each: `10.0.0.11` (node 1, local) and `10.0.0.12` (node 2).
- Expected votes 2, quorum 1, flags `2Node Quorate WaitForAll`: corosync's two-node mode is on.
- Transport `knet`, secure auth on, config version 4.

## Entities mentioned

[[entities/host-pve1]], [[entities/host-pve2]]

## Concepts mentioned

[[concepts/two-node-quorum]]
