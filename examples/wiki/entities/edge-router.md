---
kind: device
status: active
last_verified: 2026-06-02
---

# edge-router

The router of `lab.example`. Its DHCP server reserves the addresses of pve1, pve2, the Raspberry
Pi, the NAS and CT 102, and tells every client to use `10.0.0.53` and `10.0.0.54` for DNS
[[sources/2026-06-02-router-dhcp]].

## Its backups live on the NAS

Every week it saves its configuration to `nfs://10.0.0.30/mnt/tank/router-backups`, which is
[[entities/vm-200-nas]], an address the router itself hands out
[[sources/2026-06-02-router-dhcp]]. See [[concepts/circular-dhcp-reservation]].

## Relations

- Reserves addresses for: [[entities/host-pve1]], [[entities/host-pve2]], [[entities/host-rpi]],
  [[entities/vm-200-nas]], [[entities/ct-102-pihole]]
- Announces DNS: [[entities/pihole]]

## Sources

- [[sources/2026-06-02-router-dhcp]]

## Update history

- 2026-06-02: first documented from its configuration export [[sources/2026-06-02-router-dhcp]]
