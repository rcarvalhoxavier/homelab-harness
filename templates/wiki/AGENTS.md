---
harness_schema: 1
mode: {{mode}}
exposure: {{exposure}}
language: {{language}}
stale_after_days: 90
pending_after_days: 14
extra_trust_levels: []
extra_entity_kinds: []
---

# Wiki schema

This file configures the agent that maintains this wiki. The **rules** — operations,
provenance, trust tiers, page formats — live in the `llm-wiki` skill and arrive with upstream
updates. This file holds only what is specific to **your** environment. Co-evolve it: when a new
kind of source or a naming need shows up, change it here and note it in the changelog below.

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

## Purpose  [CUSTOMIZE]

Knowledge base about the **live infrastructure** of this environment: what runs where, in which
version, why, what broke, and what was learned each time something changed.

## Scope  [CUSTOMIZE]

In:

- Hosts, guests, services, devices, storage and networks as entities with state and history
- Operational decisions and the reasoning behind them
- Changes, incidents and upgrades, with their evidence
- External sources: vendor docs, changelogs, threads, third-party scripts

Out:

- Step-by-step procedures: write runbooks and link them
- Specs and plans for the code in this repo: `local/docs/` (set in `.claude/rules/local.md`)
- Secrets of any kind, in any page or capture

## Boundary with other docs  [CUSTOMIZE]

| Where | Owns |
|---|---|
| `wiki/` | Knowledge about the infrastructure |
| `local/` | Your scripts and stacks |

An entity with no history of its own does not get a page; point to the guest table in `overview.md` instead.

## Entity kinds in use  [CUSTOMIZE]

| kind | Meaning | Filename |
|---|---|---|
| `host` | Physical machine: hypervisor node, Raspberry Pi, NAS box | `entities/host-<name>.md` |
| `guest` | LXC container or VM | `entities/ct-<id>-<name>.md`, `entities/vm-<id>-<name>.md` |
| `service` | Software running somewhere | `entities/<name>.md` |
| `device` | Network or IoT hardware outside the hypervisor | `entities/<name>.md` |
| `storage` | Storage target or pool | `entities/storage-<name>.md` |
| `network` | Subnet, VLAN, DNS zone, tunnel | `entities/net-<name>.md` |
| `external` | Upstream project, script collection, SaaS dependency | `entities/<name>.md` |
| `system` | Several entities treated as one unit, such as a media pipeline | `entities/<name>.md` |

Delete the rows you do not use. For a new kind, add a row here and its name to
`extra_entity_kinds` in the frontmatter.

## Naming overrides  [CUSTOMIZE]

None. Defaults come from the `llm-wiki` skill (`references/page-formats.md`).

## Extra trust tiers  [CUSTOMIZE]

None. The base tiers are `measured`, `internal-reviewed`, `vendor`, `third-party`, `user`,
`agent-report` and `web`; see the `llm-wiki` skill.

## Vocabulary  [CUSTOMIZE]

| Term used here | Avoid |
|---|---|
| (your node names, and what they must never be "corrected" to) | |

## Schema changelog

- {{date}}: created by `bin/init`.
