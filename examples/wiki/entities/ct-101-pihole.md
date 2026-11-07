---
kind: guest
status: active
last_verified: 2026-06-14
---

# CT 101 — pihole

The primary DNS server of the lab: an LXC container on pve1, allowed 1024 MiB, with its disk on
`local-lvm` [[sources/2026-06-01-guests]]. It runs [[entities/pihole]], on Core `v6.1.2` since
2026-06-14 [[sources/2026-06-14-pihole-after]].

## Address

Its address, `10.0.0.53/24`, is static and lives in the container's own config
[[sources/2026-06-02-guest-network]]. Unlike [[entities/ct-102-pihole]], a restore from backup
brings the address back with the container.

## Snapshot

The snapshot `pre-pihole-v6`, taken on 2026-06-14 at 20:05:31 right before the upgrade, exists
since then [[sources/2026-06-14-pihole-after]]. When to remove it is an open decision of the
admin, tracked in [[changes/2026-06-14-pihole-v6-upgrade]]. It is possible because the container
lives on a thin pool; see [[concepts/snapshot-depends-on-storage]].

## Relations

- Runs: [[entities/pihole]]
- On: [[entities/host-pve1]], storage [[entities/storage-local-lvm]]
- Peer: [[entities/ct-102-pihole]]

## Sources

- [[sources/2026-06-01-guests]]
- [[sources/2026-06-02-guest-network]]
- [[sources/2026-06-14-pihole-baseline]]
- [[sources/2026-06-14-pihole-simulation]]
- [[sources/2026-06-14-pihole-snapshot]]
- [[sources/2026-06-14-pihole-after]]
- [[sources/2026-06-20-pihole-pair]]

## Update history

- 2026-06-14: Pi-hole upgraded from v5 to v6 [[changes/2026-06-14-pihole-v6-upgrade]]
- 2026-06-01: first documented from the guest inventory [[sources/2026-06-01-guests]]
