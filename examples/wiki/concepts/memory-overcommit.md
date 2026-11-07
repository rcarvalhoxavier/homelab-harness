# Memory overcommit

## Definition

The guests of a node are allowed more memory, in total, than the node physically has. It works
while they do not all use their allowance at once; when they do, the node swaps
[[sources/2026-06-01-guests]] [[sources/2026-06-01-pve-versions]].

## The case in this lab

On pve1 the guests' allowances add up to 37888 MiB against 31958 MiB of RAM, about 119 %
[[sources/2026-06-01-guests]] [[sources/2026-06-01-pve-versions]]. On 2026-06-01 pve1 had
6210 MiB of swap in use, while pve2, with a single 512 MiB guest, had none
[[sources/2026-06-01-pve-versions]].

## Occurrences

- [[entities/host-pve1]]
- [[entities/host-pve2]]

## Notes and contradictions

None.
