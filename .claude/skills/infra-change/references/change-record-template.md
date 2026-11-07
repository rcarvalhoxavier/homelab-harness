---
date: YYYY-MM-DD
targets: [entities/<target>]
outcome: planned
rollback: snapshot
baseline: sources/YYYY-MM-DD-<target>-baseline
---

<!--
Frontmatter notes:
- add `after: sources/YYYY-MM-DD-<target>-after` once the after-capture exists
- a change recorded after the fact with no earlier capture: replace `baseline:` with
  `baseline_unavailable: <reason>` (see references/situations.md)
- code behind the change: `specs: [local/docs/specs/<file>.md]`, `plans: [local/docs/plans/<file>.md]`
-->

# <What changes, in one line>

## Goal

<Why this change.>

**Path:** <trivial | standard | risky>, because <reason>.

**Done when** (collector lines that must show it after the change):

- `<command>` shows <expected value>
- `<functional check>` answers <expected result>

**Abort if:** <conditions that stop the change and trigger the rollback>

**Approved by** <user> on <date>, for the plan below.

## Collector

The exact read-only commands used for the baseline and for the after-capture:

```bash
<command 1>
<command 2>
```

## Reversibility

- **Rollback:** <snapshot `<name>` on <storage> | backup <file> | none | other>
- **Confirmed before the change:** <how: snapshot listed, backup verified restorable; with citation>
- **Simulation** (required when rollback is `none`, and for risky changes): <[[sources/YYYY-MM-DD-<target>-simulation]] or the user's explicit acknowledgment>

## Execution

Each line is written before the command runs; its result right after.

1. `<command>` on <host> (confirmed by <user>): <result>
2. `<command>`: <result>

## Diff

<Baseline vs after: what changed and what did not, citing both sources. Quote each done-criterion
as it appears in the after-capture.>

## Outcome

<done | rolled-back | aborted, and why.>

## Pending

- [ ] <Follow-up decision> — owner: <user | name>

## Links

<Runbooks used; parent or child change records; anything else a later reader needs.>
