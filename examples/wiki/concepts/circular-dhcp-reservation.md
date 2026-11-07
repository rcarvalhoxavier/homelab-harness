# Circular DHCP reservation

## Definition

A loop between an address and the device that hands it out: a device keeps its own backup on a
host whose address depends on that same device [[sources/2026-06-02-router-dhcp]].

## The case in this lab

The NAS, VM 200, has no address in its config, only the MAC `BC:24:11:00:02:00`
[[sources/2026-06-02-guest-network]]. The router reserves `10.0.0.30` for that MAC, and saves its
own configuration every week to `nfs://10.0.0.30/mnt/tank/router-backups`
[[sources/2026-06-02-router-dhcp]].

## Consequences

Restoring a broken router needs its backup from the NAS, but the NAS gets its address from the
router, so the restore order has to be planned ahead: bring the NAS up with a temporary static
address, or keep a copy of the router backup somewhere else [[sources/2026-06-02-router-dhcp]].
Restoring VM 200 with a new MAC loses the reservation as well
[[sources/2026-06-02-guest-network]].

## Occurrences

- [[entities/edge-router]]
- [[entities/vm-200-nas]]
- [[entities/ct-102-pihole]]: the same address-outside-the-guest pattern, without the loop

## Notes and contradictions

None.
