---
title: Admin notes about the Raspberry Pi
date: 2026-06-02
type: conversation
source: raw/2026-06-02-rpi-admin-notes.txt
source_hash: aa8c25390e1ce8b9
trust_level: user
origin: "admin, in chat"
redactions: {secret: 0, ip: 0, mac: 0}
---

## Summary

What the admin said about the Raspberry Pi on 2026-06-02. Tier `user`: authoritative on what
was set up and why, not on the Pi's current state, and not verified against it.

## Key points

- A 4 GB Raspberry Pi 4 booting from a USB SSD, on the same UPS as pve1.
- Runs Home Assistant OS with the Mosquitto broker add-on; Zigbee goes through a USB dongle on
  the Pi.
- Set up in 2025, and kept off Proxmox because of the dongle.
- Verification: the USB SSD is consistent with the data disk `/dev/sda`
  [[sources/2026-03-10-rpi-ha-info]]; everything else is unverified.

## Entities mentioned

[[entities/host-rpi]], [[entities/home-assistant]]

## Concepts mentioned

None.
