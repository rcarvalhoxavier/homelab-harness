---
title: Snapshot of CT 101 confirmed before the upgrade
date: 2026-06-14
type: measurement
source: raw/2026-06-14-pihole-snapshot.txt
source_hash: 34145b0ede23a494
trust_level: measured
origin: "pct listsnapshot 101 @ pve1, right after pct snapshot, before pihole -up"
redactions: {secret: 0, ip: 0, mac: 0}
---

## Summary

The rollback of [[changes/2026-06-14-pihole-v6-upgrade]], confirmed before anything changed:
`pct listsnapshot 101` right after the snapshot was taken, before `pihole -up`.

## Key points

- Snapshot `pre-pihole-v6` exists, taken 2026-06-14 20:05:31, "before the v6 upgrade".

## Entities mentioned

[[entities/ct-101-pihole]], [[entities/storage-local-lvm]]

## Concepts mentioned

[[concepts/reversibility-by-infrastructure]]
