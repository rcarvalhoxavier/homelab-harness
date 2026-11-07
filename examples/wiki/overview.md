# Overview — lab.example

_Synthesis of the environment's current state. Rewritten as knowledge accumulates._
_Last updated: 2026-06-20._

> Fictional example environment. Start here, then follow the links.

## Hosts

Two Proxmox nodes form the cluster `lab`. [[entities/host-pve1]] carries almost every guest and
runs short of memory ([[concepts/memory-overcommit]]); [[entities/host-pve2]] carries only the
secondary DNS server. With two nodes, quorum relies on corosync's two-node mode
([[concepts/two-node-quorum]]). A Raspberry Pi, [[entities/host-rpi]], runs
[[entities/home-assistant]] outside Proxmox.

## Guests

Every guest on 2026-06-01, all running ([[sources/2026-06-01-guests]]). A guest gets its own page
once something happens to it.

| Guest | Name | Node | Memory (MiB) | Page |
|---|---|---|---|---|
| CT 101 | `pihole` | pve1 | 1024 | [[entities/ct-101-pihole]] |
| CT 102 | `pihole2` | pve2 | 512 | [[entities/ct-102-pihole]] |
| CT 105 | `media` | pve1 | 8192 | — |
| CT 106 | `docker` | pve1 | 12288 | — |
| VM 200 | `nas` | pve1 | 16384 | [[entities/vm-200-nas]] |

## Network and DNS

[[entities/edge-router]] hands out addresses and DNS servers. DNS is [[entities/pihole]], on
[[entities/ct-101-pihole]] and [[entities/ct-102-pihole]]; the pair is only partly redundant
([[analyses/2026-06-20-pihole-pair-redundancy]]). Some addresses live in the router rather than
in the guests, and one of those dependencies is a loop ([[concepts/circular-dhcp-reservation]]).

## Storage and backup

[[entities/vm-200-nas]] serves [[entities/storage-nas-backup]], the target of the nightly
backups, and is itself excluded from them. Snapshots work on [[entities/storage-local-lvm]], not
for disks on directory storage ([[concepts/snapshot-depends-on-storage]]).

## Recent changes

- 2026-06-14: Pi-hole v5 to v6 on CT 101 ([[changes/2026-06-14-pihole-v6-upgrade]]), made
  reversible by a snapshot ([[concepts/reversibility-by-infrastructure]]) and simulated first
  ([[concepts/simulate-before-irreversible]]). One decision is still pending.

## Open questions

- The Pi-hole version on CT 102 has never been captured.
- The Raspberry Pi was last measured on 2026-03-10.
