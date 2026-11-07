# Page formats

## Naming

Kebab-case everywhere. `wiki/AGENTS.md` may override these defaults.

| Page | Filename |
|---|---|
| host (hypervisor node, Raspberry Pi, NAS box) | `entities/host-<name>.md` |
| guest (container or VM) | `entities/ct-<id>-<name>.md`, `entities/vm-<id>-<name>.md` |
| service, device, external, system | `entities/<name>.md` |
| storage | `entities/storage-<name>.md` |
| network | `entities/net-<name>.md` |
| concept | `concepts/<name>.md` |
| source | `sources/YYYY-MM-DD-<slug>.md`, created by `bin/wiki-capture` |
| change record | `changes/YYYY-MM-DD-<slug>.md` |
| analysis | `analyses/YYYY-MM-DD-<slug>.md` |

## Frontmatter

A flat subset of YAML: one `key: value` per line; strings plain or quoted; integers; `true`
and `false`; lists inline (`[a, b]`) or as `  - item` lines under their key (the form Obsidian's
properties editor writes); maps inline (`{secret: 0, ip: 0}`). No nesting beyond that. A page
whose frontmatter does not parse is `E-FRONTMATTER` (or the page type's own `E-*-FIELD`).

## Links

- `[[entities/ct-101-pihole]]`: relative to the wiki root, without `.md`.
- `[[entities/pihole|Pi-hole]]` for a different label; `[[concepts/two-node-quorum#Case]]` for a
  heading.
- Files outside the wiki: a normal path in backticks, such as `docs/runbook.md`.
- The tools ignore links inside fenced code and inline code, so `[[ -n "$x" ]]` in a shell
  snippet is safe.
- Cross-references go both ways: if A links B because they are related, B links A.

## Entity

```markdown
---
kind: guest
status: active
last_verified: 2026-06-14
---

# CT 101 — pihole

What it is, where it runs and why it matters, with a citation [[sources/2026-06-01-guests]].

## <Topic sections as needed>

## Relations

- Runs: [[entities/pihole]]
- On: [[entities/host-pve1]]

## Sources

- [[sources/2026-06-01-guests]]

## Update history

- 2026-06-14: Pi-hole v5 to v6 [[changes/2026-06-14-pihole-v6-upgrade]]
```

- `kind`: `host`, `guest`, `service`, `device`, `storage`, `network`, `external`, `system`, plus
  any name in `extra_entity_kinds`.
- `status`: `active`, `retired`, `evaluating`.
- `last_verified`: see `trust-and-provenance.md`.

## Concept

```markdown
# <Name>

## Definition

The pattern in two or three sentences, with a citation to where it was seen [[sources/...]].

## The case that established it

What happened, cited.

## Occurrences

- [[entities/...]]

## Notes and contradictions
```

## Source

Created by `bin/wiki-capture`; INGEST replaces the `TODO(ingest)` markers.

```markdown
---
title: Pi-hole on CT 101 after the v6 upgrade
date: 2026-06-14
type: measurement
source: raw/2026-06-14-pihole-after.txt
source_hash: 0123456789abcdef
trust_level: measured
origin: "collector pihole-state @ ct-101"
redactions: {secret: 0, ip: 0, mac: 0, host: 0}
---

## Summary

## Key points

## Entities mentioned

## Concepts mentioned
```

- Required: `title`, `date` (date of the evidence), `type`, `source`, `source_hash`,
  `trust_level`.
- `type`: `measurement`, `document`, `report`, `article`, `changelog`, `conversation`.
- `source`: a `raw/` path, or the path of a file versioned in this repo, never outside either.
  Never a URL: save the page to `raw/` and put its address in the optional `url:` field.
- Optional, written by `bin/wiki-capture`: `origin`, `redactions`, and `encoding` when the
  input was not UTF-8.
- Several source pages may cite the same raw file: a re-verification that found identical
  evidence gets its own dated source page.

## Change record

Created by the `infra-change` skill from its `references/change-record-template.md`.

- Frontmatter: `date`, `targets` (list of entity pages), `outcome` (`planned`, `done`,
  `rolled-back`, `aborted`), `rollback` (`snapshot`, `backup`, `none`, `other`), `baseline` (the
  baseline source), `after` (added once the after-capture exists). Optional: `specs` and `plans`
  (repository paths of the code behind the change), `baseline_unavailable: <reason>` for a
  change recorded after the fact.
- `done` and `rolled-back` require `after`, and `baseline` or `baseline_unavailable`.
- Sections: Goal (with the path, the done-criteria, the abort conditions and the approval),
  Collector, Reversibility, Execution, Diff, Outcome, Pending, Links. Each pending item is a
  checkbox that names its owner:
  `- [ ] Remove snapshot pre-upgrade after a week of real use — owner: user`.

## Analysis

```markdown
---
question: Is the Pi-hole pair actually redundant?
---

# <The question>

The answer, with citations, then what would change it.
```

An incident note from DIAGNOSE is an analysis named `analyses/YYYY-MM-DD-incident-<slug>.md`, with
`question: why is <X> failing?` and sections Symptom, Recent changes, Hypotheses (refuted ones
struck through, never deleted), Verdict and Fix (a link to the change record).

## `index.md` and `log.md`

- `index.md`: one line per page, `- [[dir/page]] — one-line summary`, grouped under a heading per
  directory.
- `log.md`: append-only, newest last. Headings are exactly
  `## [YYYY-MM-DD] <op> | <title>`, where op is one of `ingest`, `query`, `lint`, `update`,
  `capture`, `change`, `diagnose`, `reconcile`. Recent entries:
  `grep "^## \[" wiki/log.md | tail -10`.

## Headings the linter reads

Two headings carry meaning for `bin/wiki-lint`, so keep them in English whatever the wiki's
language:

- `## Pending` in change records: every `- [ ]` below it is an open item (`W-PENDING`). The
  linter accepts any heading that starts with "Pend".
- `## ⚠️ Contradiction`: an unresolved contradiction (`W-CONTRADICTION`). The linter matches a
  heading that starts with "Contrad", with or without the ⚠️. A section named "Notes and
  contradictions" does not match.

## Universal vocabulary

| Use | Do not confuse with |
|---|---|
| **snapshot**: point-in-time state on the same storage, rolled back in seconds; depends on the storage type | **backup**: a copy on another storage (`vzdump` archive) that survives losing the host |
| **node / host**: the physical machine | **guest**: a container or VM on it; **service**: the software a guest runs |
| **thin pool free space**: room left inside an LVM thin pool | **VG free space**: room left to grow the pool itself |
| **DHCP reservation**: the address lives in the DHCP server | **static address**: the address lives in the guest's own config |
