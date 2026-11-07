---
title: NFS storage definition
date: 2026-06-01
type: measurement
source: raw/2026-06-01-storage-config.txt
source_hash: af24c6fb622c1d54
trust_level: measured
origin: "grep -A5 '^nfs: nas-backup' /etc/pve/storage.cfg @ pve1"
redactions: {secret: 0, ip: 0, mac: 0}
---

## Summary

The definition of the `nas-backup` storage in `/etc/pve/storage.cfg` on pve1, 2026-06-01.

## Key points

- NFS storage served by `10.0.0.30`, export `/mnt/tank/proxmox-backups`, mounted at
  `/mnt/pve/nas-backup`.
- Content: backups only.

## Entities mentioned

[[entities/storage-nas-backup]], [[entities/vm-200-nas]]

## Concepts mentioned

None.
