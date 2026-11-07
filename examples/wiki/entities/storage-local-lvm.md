---
kind: storage
status: active
last_verified: 2026-06-01
---

# storage local-lvm

The LVM thin pool of pve1, 62.40 % used on 2026-06-01 [[sources/2026-06-01-storage]]. It holds
CT 101, CT 105, CT 106 and one of the disks of VM 200 [[sources/2026-06-01-guests]].

Being a thin pool, it supports snapshots: the `pre-pihole-v6` snapshot of CT 101 lives here
[[sources/2026-06-14-pihole-after]]. See [[concepts/snapshot-depends-on-storage]].

## Relations

- On: [[entities/host-pve1]]
- Holds: [[entities/ct-101-pihole]], [[entities/vm-200-nas]]

## Sources

- [[sources/2026-06-01-storage]]
- [[sources/2026-06-01-guests]]
- [[sources/2026-06-14-pihole-after]]

## Update history

- 2026-06-01: first documented [[sources/2026-06-01-storage]]
