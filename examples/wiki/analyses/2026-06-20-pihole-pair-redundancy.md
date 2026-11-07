---
question: Is the Pi-hole pair actually redundant?
---

# Is the Pi-hole pair actually redundant?

**Partly.** The two instances run on different nodes, CT 101 on pve1 and CT 102 on pve2
[[sources/2026-06-01-guests]], and every client is given both addresses
[[sources/2026-06-02-router-dhcp]], so losing one node does not take DNS down.

But they are not interchangeable. In the week to 2026-06-20, CT 101 answered about 91 % of the
queries (412381 of 451288), and CT 102 is missing three local records: `nas.lab.example`,
`rpi.lab.example` and `backup.lab.example` [[sources/2026-06-20-pihole-pair]]. While CT 101 is
down, internet names keep resolving and those three local names stop resolving.

## What would change the answer

Keeping the local records of both instances in sync, by hand or with a sync tool, would make the
pair fully redundant. A new capture of both instances' records would confirm it.

Pages: [[entities/pihole]], [[entities/ct-101-pihole]], [[entities/ct-102-pihole]].
