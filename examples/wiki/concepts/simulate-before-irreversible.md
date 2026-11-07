# Simulate before the irreversible step

## Definition

Before a step with no way back of its own, run the simulation the tooling offers (`apt-get -s`,
`--dry-run`, `--check-only`) and read its output as a prediction to check against the plan,
instead of trusting a reading of scripts or docs [[sources/2026-06-14-pihole-simulation]].

## The case that established it

The Pi-hole upgrade on CT 101 was one-way for Pi-hole itself, with a snapshot as the only way
back [[changes/2026-06-14-pihole-v6-upgrade]]. Before it, `pihole -up --check-only` confirmed
updates for Core, the web interface and FTL, and `apt-get -s dist-upgrade` predicted three
packages upgraded and none removed [[sources/2026-06-14-pihole-simulation]]. The upgrade then
went exactly as predicted [[sources/2026-06-14-pihole-after]].

## Occurrences

- [[changes/2026-06-14-pihole-v6-upgrade]]
- [[entities/ct-101-pihole]]

## Notes and contradictions

None.
