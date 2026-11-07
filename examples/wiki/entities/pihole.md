---
kind: service
status: active
last_verified: 2026-06-20
---

# Pi-hole

The lab's DNS filter, run as two instances: [[entities/ct-101-pihole]] on pve1 and
[[entities/ct-102-pihole]] on pve2 [[sources/2026-06-01-guests]]. The router gives both
addresses, `10.0.0.53` and `10.0.0.54`, to every client [[sources/2026-06-02-router-dhcp]].

## Versions

CT 101 runs Core `v6.1.2`, Web `v6.2.1` and FTL `v6.1` since the upgrade of 2026-06-14
[[changes/2026-06-14-pihole-v6-upgrade]] [[sources/2026-06-14-pihole-after]]. The version on
CT 102 has never been captured.

## Redundancy

About 91 % of the week's queries went to CT 101, and CT 102 lacks three local records
[[sources/2026-06-20-pihole-pair]]. The pair survives a node failure for internet names but not
for local ones: [[analyses/2026-06-20-pihole-pair-redundancy]].

## Relations

- Instances: [[entities/ct-101-pihole]], [[entities/ct-102-pihole]]
- Announced by: [[entities/edge-router]]

## Sources

- [[sources/2026-06-01-guests]]
- [[sources/2026-06-02-router-dhcp]]
- [[sources/2026-06-14-pihole-baseline]]
- [[sources/2026-06-14-pihole-after]]
- [[sources/2026-06-20-pihole-pair]]

## Update history

- 2026-06-20: query share and local records compared [[sources/2026-06-20-pihole-pair]]
- 2026-06-14: CT 101 upgraded from v5 to v6 [[changes/2026-06-14-pihole-v6-upgrade]]
