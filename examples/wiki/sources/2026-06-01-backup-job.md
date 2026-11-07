---
title: Nightly backup job
date: 2026-06-01
type: measurement
source: raw/2026-06-01-backup-job.txt
source_hash: e2e09ae3cca34257
trust_level: measured
origin: cat /etc/pve/jobs.cfg @ pve1
redactions: {secret: 0, ip: 0, mac: 0}
---

## Summary

The only scheduled backup job of the cluster, from `/etc/pve/jobs.cfg` on pve1, 2026-06-01.

## Key points

- Job `backup-nightly`, enabled: every guest except 200, daily at 23:00.
- Snapshot mode, zstd compression, to `nas-backup`, keeping the last 3.

## Entities mentioned

[[entities/storage-nas-backup]], [[entities/vm-200-nas]]

## Concepts mentioned

None.
