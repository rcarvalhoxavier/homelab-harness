---
kind: host
status: active
last_verified: 2026-03-10
---

# host-rpi

A Raspberry Pi 4 (`raspberrypi4-64`, `aarch64`) running Home Assistant OS `15.0`, with its data
disk at `/dev/sda` [[sources/2026-03-10-rpi-ha-info]]. Its address, `10.0.0.20`, is reserved on
the router [[sources/2026-06-02-router-dhcp]]. It runs [[entities/home-assistant]].

## What the admin says

Per the admin (tier `user`, not verified on the Pi): it is the 4 GB model, boots from a USB SSD,
shares the UPS of pve1, and stays outside Proxmox because Zigbee goes through a USB dongle
plugged into it [[sources/2026-06-02-rpi-admin-notes]]. The USB SSD is consistent with a data
disk at `/dev/sda` [[sources/2026-03-10-rpi-ha-info]].

## Relations

- Runs: [[entities/home-assistant]]
- Shares a UPS with, per the admin: [[entities/host-pve1]]

## Sources

- [[sources/2026-03-10-rpi-ha-info]]
- [[sources/2026-06-02-rpi-admin-notes]]
- [[sources/2026-06-02-router-dhcp]]

## Update history

- 2026-06-02: the admin's notes added, tier `user` [[sources/2026-06-02-rpi-admin-notes]]
- 2026-03-10: first capture [[sources/2026-03-10-rpi-ha-info]]
