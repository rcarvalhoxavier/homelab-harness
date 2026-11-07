---
kind: guest
status: active
last_verified: 2026-06-20
---

# CT 102 — pihole2

The secondary DNS server: an LXC container on pve2, allowed 512 MiB [[sources/2026-06-01-guests]].
It runs the second instance of [[entities/pihole]].

## The address lives in the router

Its config says `ip=dhcp` [[sources/2026-06-02-guest-network]]. The address clients are told to
use, `10.0.0.54`, comes from a reservation on [[entities/edge-router]] keyed on the container's
MAC [[sources/2026-06-02-router-dhcp]]. The container config alone shows no address, and a
restore with a new MAC would lose it.

## Out of sync with CT 101

In the week to 2026-06-20 it answered 38907 queries against 412381 on CT 101, and it held 11
local DNS records against 14: `nas`, `rpi` and `backup.lab.example` are missing
[[sources/2026-06-20-pihole-pair]]. See [[analyses/2026-06-20-pihole-pair-redundancy]].

## Relations

- Runs: [[entities/pihole]]
- On: [[entities/host-pve2]]
- Peer: [[entities/ct-101-pihole]]
- Pattern: [[concepts/circular-dhcp-reservation]] (the address lives outside the guest)

## Sources

- [[sources/2026-06-01-guests]]
- [[sources/2026-06-02-guest-network]]
- [[sources/2026-06-02-router-dhcp]]
- [[sources/2026-06-20-pihole-pair]]

## Update history

- 2026-06-20: query share and local records compared with CT 101 [[sources/2026-06-20-pihole-pair]]
- 2026-06-02: address traced to the router reservation [[sources/2026-06-02-router-dhcp]]
