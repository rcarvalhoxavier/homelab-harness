---
kind: guest
status: active
last_verified: 2026-06-02
---

# VM 200 — nas

The lab's NAS: a VM on pve1, allowed 16384 MiB, with disks on `local-lvm` and on `data-dir`
[[sources/2026-06-01-guests]]. At `10.0.0.30` it serves the NFS storage
[[entities/storage-nas-backup]] [[sources/2026-06-01-storage-config]]
[[sources/2026-06-02-router-dhcp]], the target of every backup [[sources/2026-06-01-backup-job]].

## No snapshot, no backup

A snapshot attempt fails because one of its disks is a raw file on the directory storage
`data-dir` [[sources/2026-06-01-storage]]; see [[concepts/snapshot-depends-on-storage]]. The
nightly job excludes it (`exclude 200`) [[sources/2026-06-01-backup-job]]: the machine that holds
every backup has none of its own.

## Address

Its config holds no address, only the MAC `BC:24:11:00:02:00` [[sources/2026-06-02-guest-network]].
The router reserves `10.0.0.30` for that MAC, and backs its own configuration up to an NFS share
at that same address [[sources/2026-06-02-router-dhcp]]. See
[[concepts/circular-dhcp-reservation]].

## Relations

- On: [[entities/host-pve1]]
- Serves: [[entities/storage-nas-backup]]
- Address from: [[entities/edge-router]]

## Sources

- [[sources/2026-06-01-guests]]
- [[sources/2026-06-01-storage]]
- [[sources/2026-06-01-storage-config]]
- [[sources/2026-06-01-backup-job]]
- [[sources/2026-06-02-guest-network]]
- [[sources/2026-06-02-router-dhcp]]

## Update history

- 2026-06-02: address traced to the router reservation [[sources/2026-06-02-router-dhcp]]
- 2026-06-01: first documented; snapshot probe failed [[sources/2026-06-01-storage]]
