# Log

Append-only; newest entry last. Heading format: `## [YYYY-MM-DD] <op> | <title>`.

## [2026-06-01] update | Wiki created

Created by `bin/init`; schema customized for `lab.example`.

## [2026-06-01] capture | Cluster, versions, guests, storage, backup job

Six captures from pve1: cluster status, versions and memory, guests, storage, storage config,
backup job. All `measured`, no redactions.

## [2026-06-01] ingest | Cluster baseline (and the 2026-03-10 Home Assistant capture)

Pages for both nodes, the storages and the guests with a history; concepts on quorum, memory
overcommit and snapshots. CT 105 and CT 106 get no page.

## [2026-06-02] ingest | Network: DHCP reservations and guest addresses

Router export and guest `net0` lines. The NAS address and the router's backup target form a loop.

## [2026-06-02] ingest | Raspberry Pi notes from the admin (trust: user)

Recorded as said; only the boot disk is consistent with a measurement.

## [2026-06-14] change | Pi-hole v5 to v6 on CT 101

Baseline, simulation, snapshot confirmed before the upgrade, upgrade, after-capture. Done;
removing the snapshot is pending.

## [2026-06-20] query | Is the Pi-hole pair redundant?

Partly: node-redundant, but CT 102 lacks three local records. Saved as an analysis.
