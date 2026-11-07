---
harness_schema: 1
mode: personal
exposure: private
language: en
stale_after_days: 90
pending_after_days: 14
extra_trust_levels: []
extra_entity_kinds: []
---

# Wiki schema

> **Fictional example.** The environment `lab.example` does not exist; addresses are private ranges.

This file configures the agent that maintains this wiki. The **rules** — operations,
provenance, trust tiers, page formats — live in the `llm-wiki` skill and arrive with upstream
updates. This file holds only what is specific to **this** environment.

The frontmatter above is read by `bin/wiki-lint` and `bin/wiki-capture`:

| Key | Meaning |
|---|---|
| `mode` | `personal` (one writer) or `team` (several writers; generated pages are reviewed before use) |
| `exposure` | `private` or `public`. In `public`, captures also redact IP and MAC addresses and the linter rejects them |
| `language` | Language the wiki pages are written in |
| `stale_after_days` | Entities whose `last_verified` is older than this are flagged for re-verification |
| `pending_after_days` | Change records with open pending items, or still `planned`, older than this are flagged |
| `extra_trust_levels` | Local trust tiers beyond the base set; describe each one below |
| `extra_entity_kinds` | Local entity kinds beyond the base set; describe each one below |

## Purpose

Knowledge base about the live infrastructure of `lab.example`: two Proxmox nodes, a Raspberry Pi
running Home Assistant, a NAS VM, a pair of Pi-hole DNS servers and the router in front of them.
What runs where, in which version, why, and what was learned each time something changed.

## Scope

In:

- The two nodes, their guests, the Raspberry Pi, the router and the storage targets
- Decisions and changes, with the evidence captured before and after
- Patterns worth remembering (quorum, snapshots, address dependencies)

Out:

- Step-by-step procedures (none in this example)
- Secrets of any kind

## Boundary with other docs

| Where | Owns |
|---|---|
| `examples/wiki/` | Everything about `lab.example`; there is no other doc in this example |

Guests 105 (`media`) and 106 (`docker`) appear in the guest inventory but have no history of
their own, so they get no page.

## Entity kinds in use

| kind | Meaning | Filename |
|---|---|---|
| `host` | The Proxmox nodes and the Raspberry Pi | `entities/host-<name>.md` |
| `guest` | LXC containers and the NAS VM | `entities/ct-<id>-<name>.md`, `entities/vm-<id>-<name>.md` |
| `service` | Pi-hole, Home Assistant | `entities/<name>.md` |
| `device` | The router | `entities/<name>.md` |
| `storage` | Storage targets seen by Proxmox | `entities/storage-<name>.md` |

## Naming overrides

None.

## Extra trust tiers

None.

## Vocabulary

| Term used here | Avoid |
|---|---|
| `pve1`, `pve2`: the two Proxmox nodes | "the server", "the main box" |
| **the NAS**: VM 200 | confusing it with the `nas-backup` storage it serves |
| `edge-router`: the gateway, DHCP server and DNS option provider | "the modem" |

## Schema changelog

- 2026-06-01: created by `bin/init`.
