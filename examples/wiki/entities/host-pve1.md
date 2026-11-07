---
kind: host
status: active
last_verified: 2026-06-01
---

# host-pve1

The main Proxmox node of the cluster `lab`, running `pve-manager/8.4.1` on kernel
`6.8.12-10-pve` [[sources/2026-06-01-pve-versions]]. It is node 1 of the two-node cluster
[[sources/2026-06-01-cluster-status]], and its address, `10.0.0.11`, is a reservation on the
router [[sources/2026-06-02-router-dhcp]].

## Memory

It has 31958 MiB of RAM; on 2026-06-01, 29870 MiB were in use and 6210 of its 8191 MiB of swap
were occupied [[sources/2026-06-01-pve-versions]]. Its guests are allowed 37888 MiB in total,
about 119 % of the physical memory [[sources/2026-06-01-guests]]. See
[[concepts/memory-overcommit]].

## Guests

| Guest | Memory (MiB) | Page |
|---|---|---|
| CT 101 `pihole` | 1024 | [[entities/ct-101-pihole]] |
| CT 105 `media` | 8192 | none: no history of its own |
| CT 106 `docker` | 12288 | none: no history of its own |
| VM 200 `nas` | 16384 | [[entities/vm-200-nas]] |

Source for the table: [[sources/2026-06-01-guests]].

## Storage

It sees the thin pool [[entities/storage-local-lvm]], the directory storage `data-dir`, and the
NFS storage [[entities/storage-nas-backup]] [[sources/2026-06-01-storage]].

## Relations

- Cluster peer: [[entities/host-pve2]]
- Quorum: [[concepts/two-node-quorum]]

## Sources

- [[sources/2026-06-01-pve-versions]]
- [[sources/2026-06-01-cluster-status]]
- [[sources/2026-06-01-guests]]
- [[sources/2026-06-01-storage]]
- [[sources/2026-06-02-router-dhcp]]

## Update history

- 2026-06-01: first documented from the cluster captures [[sources/2026-06-01-pve-versions]]
