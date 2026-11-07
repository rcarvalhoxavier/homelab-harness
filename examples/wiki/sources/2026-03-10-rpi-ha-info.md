---
title: Home Assistant host info
date: 2026-03-10
type: measurement
source: raw/2026-03-10-rpi-ha-info.txt
source_hash: 1a3d15ba9317792d
trust_level: measured
origin: ha core info; ha os info @ rpi
redactions: {secret: 0, ip: 0, mac: 0}
---

## Summary

`ha core info` and `ha os info` on the Raspberry Pi, captured on 2026-03-10: the Home Assistant
Core and OS versions, and the hardware they run on.

## Key points

- Home Assistant Core `2026.3.1`, the latest at capture time; port `8123`; `ssl: false`.
- Home Assistant OS `15.0` on board `rpi4-64` (machine `raspberrypi4-64`, `aarch64`); data disk `/dev/sda`.
- The address Core reports: `10.0.0.20`.

## Entities mentioned

[[entities/host-rpi]], [[entities/home-assistant]]

## Concepts mentioned

None.
