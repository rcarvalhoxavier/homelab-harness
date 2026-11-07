---
kind: service
status: active
last_verified: 2026-03-10
---

# Home Assistant

Home Assistant Core `2026.3.1` on Home Assistant OS `15.0`, listening on port `8123` without TLS
(`ssl: false`), on [[entities/host-rpi]] [[sources/2026-03-10-rpi-ha-info]].

Per the admin (tier `user`, not verified): it runs the Mosquitto broker add-on, and Zigbee
devices reach it through a USB dongle on the Pi [[sources/2026-06-02-rpi-admin-notes]].

## Relations

- Runs on: [[entities/host-rpi]]

## Sources

- [[sources/2026-03-10-rpi-ha-info]]
- [[sources/2026-06-02-rpi-admin-notes]]

## Update history

- 2026-06-02: add-on and Zigbee setup from the admin, tier `user` [[sources/2026-06-02-rpi-admin-notes]]
- 2026-03-10: first capture [[sources/2026-03-10-rpi-ha-info]]
