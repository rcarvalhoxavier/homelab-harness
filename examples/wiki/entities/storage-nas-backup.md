---
kind: storage
status: active
last_verified: 2026-06-01
---

# storage nas-backup

An NFS storage served by `10.0.0.30`, for backups only [[sources/2026-06-01-storage-config]], and
31.00 % used on 2026-06-01 [[sources/2026-06-01-storage]]. `10.0.0.30` is the NAS,
[[entities/vm-200-nas]] [[sources/2026-06-02-router-dhcp]].

Every guest except VM 200 is backed up here nightly at 23:00, in snapshot mode with zstd,
keeping the last three [[sources/2026-06-01-backup-job]]. The NAS that serves this storage is
the one guest with no backup.

## Relations

- Served by: [[entities/vm-200-nas]]
- Seen from: [[entities/host-pve1]]

## Sources

- [[sources/2026-06-01-storage-config]]
- [[sources/2026-06-01-storage]]
- [[sources/2026-06-01-backup-job]]
- [[sources/2026-06-02-router-dhcp]]

## Update history

- 2026-06-01: first documented [[sources/2026-06-01-storage-config]]
