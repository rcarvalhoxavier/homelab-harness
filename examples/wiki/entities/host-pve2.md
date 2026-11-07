---
kind: host
status: active
last_verified: 2026-06-01
---

# host-pve2

The second Proxmox node of the cluster `lab`, on the same `pve-manager/8.4.1` and kernel
`6.8.12-10-pve` as pve1 [[sources/2026-06-01-pve-versions]]. It is node 2 of the cluster
[[sources/2026-06-01-cluster-status]], with the address `10.0.0.12` reserved on the router
[[sources/2026-06-02-router-dhcp]].

## Memory

It has 15894 MiB of RAM; on 2026-06-01 it used 6124 MiB and no swap, far from the pressure on
pve1 [[sources/2026-06-01-pve-versions]]. Its only guest is [[entities/ct-102-pihole]], allowed
512 MiB [[sources/2026-06-01-guests]].

## Relations

- Cluster peer: [[entities/host-pve1]]
- Quorum: [[concepts/two-node-quorum]]
- Memory, by contrast with pve1: [[concepts/memory-overcommit]]

## Sources

- [[sources/2026-06-01-pve-versions]]
- [[sources/2026-06-01-cluster-status]]
- [[sources/2026-06-01-guests]]
- [[sources/2026-06-02-router-dhcp]]

## Update history

- 2026-06-01: first documented from the cluster captures [[sources/2026-06-01-pve-versions]]
