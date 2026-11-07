# Index

Catalog of every page of the `lab.example` wiki, one line each.

## Entities

- [[entities/host-pve1]] — main node: pve-manager 8.4.1, memory overcommitted, most guests
- [[entities/host-pve2]] — second node: one guest, no memory pressure
- [[entities/host-rpi]] — Raspberry Pi 4 running Home Assistant OS, outside Proxmox
- [[entities/ct-101-pihole]] — primary DNS, static address, snapshot `pre-pihole-v6` pending removal
- [[entities/ct-102-pihole]] — secondary DNS, address from the router, missing three local records
- [[entities/vm-200-nas]] — the NAS: serves every backup, has none, no snapshot possible
- [[entities/edge-router]] — router: DHCP reservations, DNS option, backs itself up to the NAS
- [[entities/storage-local-lvm]] — thin pool of pve1, 62.40 % used, supports snapshots
- [[entities/storage-nas-backup]] — NFS backup target served by the NAS
- [[entities/pihole]] — DNS filter, two instances, only partly redundant
- [[entities/home-assistant]] — Home Assistant 2026.3.1 on the Raspberry Pi

## Concepts

- [[concepts/snapshot-depends-on-storage]] — thin pool yes, raw file on directory storage no
- [[concepts/two-node-quorum]] — `2Node` and `WaitForAll` in a two-node cluster
- [[concepts/simulate-before-irreversible]] — read the simulation as a prediction before a one-way step
- [[concepts/circular-dhcp-reservation]] — the router's backup lives on a host whose address the router gives
- [[concepts/reversibility-by-infrastructure]] — a snapshot as the undo that the software lacks
- [[concepts/memory-overcommit]] — guests allowed 119 % of pve1's RAM

## Changes

- [[changes/2026-06-14-pihole-v6-upgrade]] — Pi-hole v5 to v6 on CT 101, done, one pending decision

## Sources

- [[sources/2026-03-10-rpi-ha-info]] — Home Assistant host info (measured)
- [[sources/2026-06-01-cluster-status]] — cluster quorum status (measured)
- [[sources/2026-06-01-pve-versions]] — node versions and memory (measured)
- [[sources/2026-06-01-guests]] — guest inventory (measured)
- [[sources/2026-06-01-storage]] — storage status and a snapshot probe (measured)
- [[sources/2026-06-01-storage-config]] — NFS storage definition (measured)
- [[sources/2026-06-01-backup-job]] — nightly backup job (measured)
- [[sources/2026-06-02-router-dhcp]] — router DHCP reservations and config backup (measured)
- [[sources/2026-06-02-guest-network]] — guest network configuration (measured)
- [[sources/2026-06-02-rpi-admin-notes]] — admin notes about the Raspberry Pi (user)
- [[sources/2026-06-14-pihole-baseline]] — Pi-hole on CT 101 before the upgrade (measured)
- [[sources/2026-06-14-pihole-simulation]] — simulations before the upgrade (measured)
- [[sources/2026-06-14-pihole-snapshot]] — rollback snapshot confirmed before the upgrade (measured)
- [[sources/2026-06-14-pihole-after]] — Pi-hole on CT 101 after the upgrade (measured)
- [[sources/2026-06-20-pihole-pair]] — query share and local records of both instances (measured)

## Analyses

- [[analyses/2026-06-20-pihole-pair-redundancy]] — is the Pi-hole pair redundant? Partly
