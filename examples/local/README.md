# Example instance extension

A fictional extension for the `lab.example` homelab of `examples/wiki/`. In your installation the
same files live under `local/` (instance-owned; upstream never ships it):

| Here | In your installation | What |
|---|---|---|
| `collect.allow` | `local/collect.allow` | Extra read-only commands for the dispatcher; `bin/pve-collect-install` installs it |
| `bin/pihole-state` | `local/bin/pihole-state` | A collector for one service, built on `lib/pve/` |
| `selftest.d/10-pihole-dns` | `local/selftest.d/10-pihole-dns` | A check `bin/pve-selftest` runs: exit 0 PASS, 1 FAIL, 77 SKIP |

`bin/pve-selftest --local-dir examples/local` runs the example check. See `docs/proxmox-toolkit.md`.
