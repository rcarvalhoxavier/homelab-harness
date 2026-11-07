---
date: 2026-06-14
targets: [entities/ct-101-pihole, entities/pihole]
outcome: done
rollback: snapshot
baseline: sources/2026-06-14-pihole-baseline
after: sources/2026-06-14-pihole-after
---

# Pi-hole v5 to v6 on CT 101

## Goal

Move the primary DNS server from Pi-hole v5 (Core `v5.18.4`) to the latest v6 release, with DNS
answering exactly as before [[sources/2026-06-14-pihole-baseline]].

**Path:** standard: one guest, reversible by snapshot, and the secondary server keeps answering
meanwhile.

**Done when:**

- `pihole -v` shows Core, Web and FTL on v6
- `pihole status` shows FTL listening on port 53 and blocking enabled
- `dig +short @127.0.0.1 nas.lab.example` answers `10.0.0.30`

**Abort if:** `pihole -up` fails, or `dig` stops answering after the upgrade.

**Approved by** the admin on 2026-06-14, for the plan below.

## Collector

The exact read-only commands used for the baseline and for the after-capture:

```bash
pihole -v
pihole status
dig +short @127.0.0.1 nas.lab.example
pct listsnapshot 101   # on pve1
```

## Reversibility

- **Rollback:** snapshot `pre-pihole-v6` of CT 101, on the thin pool `local-lvm`
- **Confirmed present, before the upgrade:** listed by `pct listsnapshot 101` right after it was
  taken [[sources/2026-06-14-pihole-snapshot]]
- **Simulation:** `pihole -up --check-only` and `apt-get -s dist-upgrade`, nothing to remove
  [[sources/2026-06-14-pihole-simulation]]

## Execution

Run on 2026-06-14 by the admin, each destructive command confirmed on its own:

1. `pct snapshot 101 pre-pihole-v6 --description "before the v6 upgrade"` on pve1, then
   `pct listsnapshot 101` to confirm it [[sources/2026-06-14-pihole-snapshot]]
2. `apt-get dist-upgrade` in CT 101
3. `pihole -up` in CT 101

## Diff

| Item | Baseline | After |
|---|---|---|
| Core | `v5.18.4` | `v6.1.2` |
| Web | `v5.21` | `v6.2.1` |
| FTL | `v5.25.2` | `v6.1` |
| FTL listening on port 53, UDP and TCP | yes | yes |
| Blocking | enabled | enabled |
| `nas.lab.example` | `10.0.0.30` | `10.0.0.30` |
| Snapshots of CT 101 | none | `pre-pihole-v6` |

Baseline [[sources/2026-06-14-pihole-baseline]], after [[sources/2026-06-14-pihole-after]]. All
three done-criteria hold in the after-capture: Core `v6.1.2`, Web `v6.2.1`, FTL `v6.1`; "FTL is
listening on port 53" and "blocking is enabled"; `nas.lab.example` answers `10.0.0.30`.

The snapshot line is the rollback itself: it was taken after the baseline, so it shows up in
the diff. Taking it before the baseline keeps the diff to the change alone.

## Outcome

Done: the three components on their latest version, DNS answering as before.

## Pending

- [ ] Remove snapshot `pre-pihole-v6` on CT 101 after one week of real use — owner: user

## Links

No code was written for this change. Related: [[concepts/simulate-before-irreversible]],
[[concepts/reversibility-by-infrastructure]].
