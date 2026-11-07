# Snapshot depends on the storage

## Definition

Whether a guest can be snapshotted depends on where its disks live, not on the guest: a disk on
a thin pool can be snapshotted, a raw file on a directory storage cannot
[[sources/2026-06-01-storage]].

## The case that established it

`qm snapshot 200 probe` failed on pve1 because VM 200 has a disk at
`data-dir:200/vm-200-disk-1.raw`, on the `dir` storage `data-dir` [[sources/2026-06-01-storage]].
CT 101, whose disk is on the thin pool `local-lvm` [[sources/2026-06-01-guests]], got its
`pre-pihole-v6` snapshot without trouble [[sources/2026-06-14-pihole-after]].

## Why it matters

A change plan that counts on a snapshot has to check the storage first. For a guest on
directory storage the rollback is a backup, which is slower, or nothing at all; the Pi-hole
upgrade could rely on a snapshot only because of where CT 101 lives
[[changes/2026-06-14-pihole-v6-upgrade]].

## Occurrences

- [[entities/vm-200-nas]]
- [[entities/ct-101-pihole]]
- [[entities/storage-local-lvm]]

## Notes and contradictions

None.
