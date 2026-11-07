# Two-node quorum

## Definition

A two-node cluster cannot keep a majority when one node is down, because one vote out of two is
not more than half. The cluster `lab` runs corosync's two-node mode instead: expected votes 2,
quorum 1, flags `2Node Quorate WaitForAll` [[sources/2026-06-01-cluster-status]].

## What the flags mean here

With `2Node`, one vote is enough, so either node alone keeps the cluster quorate. `WaitForAll`
adds a condition after a full cold start: the nodes must have seen each other once before that
rule applies, which prevents two isolated nodes from both acting alone
[[sources/2026-06-01-cluster-status]].

## Occurrences

- [[entities/host-pve1]]
- [[entities/host-pve2]]

## Notes and contradictions

None.
