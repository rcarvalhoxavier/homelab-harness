# Reversibility by infrastructure

## Definition

When a piece of software has no undo of its own, the way back comes from the infrastructure
under it: a snapshot of the guest, taken right before the change
[[changes/2026-06-14-pihole-v6-upgrade]].

## The case that established it

The Pi-hole v6 upgrade on CT 101 was treated as one-way for Pi-hole itself. Its rollback was the
snapshot `pre-pihole-v6` on the thin pool, taken on 2026-06-14 at 20:05:31
[[changes/2026-06-14-pihole-v6-upgrade]] [[sources/2026-06-14-pihole-after]].

## The price

The snapshot keeps using thin-pool space until someone removes it, which is why its removal is a
pending decision with an owner in the change record [[changes/2026-06-14-pihole-v6-upgrade]].

## Occurrences

- [[entities/ct-101-pihole]]
- [[concepts/snapshot-depends-on-storage]]

## Notes and contradictions

None.
