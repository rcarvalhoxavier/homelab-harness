---
name: infra-change
description: >
  Plans, runs and records an operational change to self-hosted infrastructure: upgrade, update,
  install, create, deploy, migrate, move, resize, reconfigure, restart, reboot, expose, replace
  or decommission a host, container, VM, service, device or storage. The change is approved as
  a whole, captured before and after with the same read-only collector, proven done by
  measurement, and recorded in the wiki. Use when the user is about to change something in
  their homelab, e.g. "upgrade Pi-hole", "migrate CT 118", "reboot pve1 for the new kernel",
  "set up Jellyfin in a new LXC", "open port 443 to the proxy". For operational changes that
  need no code this replaces brainstorming. Not for questions about past changes (llm-wiki
  QUERY) and not for writing code (superpowers, which hands over here to deploy).
---

# Infrastructure change

Runs an operational change so that it can be reversed, and records it so that it can be
understood later. Evidence and record land in the wiki through the `llm-wiki` skill: captures
with `bin/wiki-capture`, the record in `wiki/changes/`, a line in each affected entity's update
history.

The pattern: agree on the plan, secure the way back (**rollback**), capture the state the
change touches (**baseline**), make the change while logging each step, capture the same state
again with the **same collector** (**after**), and call it done only when the after-capture
shows the done-criteria.

## Hard rules

1. **The user approves the whole plan before anything runs** (step 3), and also confirms each
   destructive command when it comes up (anything that writes, restarts, deletes, upgrades or
   migrates). A general "go ahead" covers neither the plan nor the next command.
2. The collector is read-only, reviewed command by command, and reused unchanged for the after.
3. The rollback is named and confirmed before the change; for a backup, confirmed *restorable*.
4. If the baseline capture fails, stop: without a baseline there is no diff and no evidence.
5. Each command is written to the record's Execution section **before** it runs, and its result
   right after. After an interruption, the record, not memory, says what already ran.
6. `outcome: done` only after the done-criteria lines were read in the after-capture and quoted
   in the Diff. Rolled-back and aborted changes are recorded with the same rigor.
7. No secrets anywhere: captures go through `bin/wiki-capture`, and you read every one of them.

## Flow

1. **Context.** Read the target entities' pages, their update history and open pending items of
   earlier changes. A target that does not exist yet (creating something) gets its entity page
   first, `status: evaluating`; see `references/situations.md`.
2. **Classify the path** (`references/situations.md`): *trivial* (reversible toggle, one
   restart), *standard*, or *risky* (irreversible, cluster-wide, storage, quorum, network path to
   the admin). Hidden complexity upgrades the path; nothing downgrades it.
3. **Plan, then stop for approval.** Present, in one message: the Goal; the **done-criteria** as
   specific collector lines ("`pihole -v` shows Core v6.x", "`dig @127.0.0.1 nas.lab` answers");
   the collector; the rollback and how it was confirmed; the ordered steps with the destructive
   ones marked; the **abort conditions**. On Proxmox, `bin/pve-state <vmid|node>` is the
   collector for a guest or a node, and a changing tool's `--dry-run` prints the exact steps and
   the suggested rollback and path for the plan; run it with `--yes` only after the user
   confirms that command. Risky path: ask a fresh reviewer (a subagent, if available) to check
   that the collector is read-only, the rollback covers the change and the order is safe. Wait
   for an explicit yes. Then create `wiki/changes/<date>-<slug>.md` from
   `references/change-record-template.md` with `outcome: planned`.
4. **Rollback first.** Take it before the baseline, so the diff shows only the change:
   ```bash
   pct snapshot <id> pre-<slug>      # destructive: needs confirmation
   pct listsnapshot <id>             # read-only: confirms it
   ```
   Not every storage supports snapshots. For a backup, prove it is restorable (list the archive,
   `proxmox-backup-client verify`, a test restore). If the rollback is `none`, run the
   simulation the tooling offers (`apt-get -s`, `--dry-run`, `-n`, `--what-if`, `--check-only`)
   and capture it; without a simulation, get explicit acknowledgment that there is no way back.
5. **Baseline.**
   ```bash
   <collector> | bin/wiki-capture <target>-baseline --origin "<collector> @ <host>"
   ```
   Read the capture and note the `raw:` path it prints.
6. **Execute.** One command at a time: write it under Execution, get confirmation if it is
   destructive, run it, write its result. Hit an abort condition: stop, go to "When it goes
   wrong".
7. **After.**
   ```bash
   <collector> | bin/wiki-capture <target>-after --origin "<collector> @ <host>"
   diff -u <baseline raw: path> <after raw: path>      # the paths the two captures printed
   ```
   `unchanged:` means the state is identical to the baseline (expected after a clean rollback,
   a finding otherwise): capture still writes a dated `sources/<date>-<target>-after.md` for the
   same raw file; use it as `after:` and write "no change" in the Diff.
8. **Done, measured.** Read each done-criterion in the after-capture and quote it in the Diff. All
   present: `outcome: done`. Otherwise it is not done; decide with the user.
9. **Record.** `after:` in the frontmatter, the Diff (changed and unchanged, citing both sources),
   the Outcome, a Pending item with an owner for every follow-up (removing the snapshot after
   some days of real use is the classic one). Then, through `llm-wiki`: complete both source
   pages, add the change to each target's `## Update history`, bump `last_verified`, update
   `index.md` and `overview.md`, log `## [YYYY-MM-DD] change | <title>`, run `bin/wiki-lint` (0
   errors).

## When it goes wrong

Stop, and tell the user what you see. Roll back with the named rollback, after their
confirmation. Capture the rolled-back state with the same collector as the `after` source.
Record `outcome: rolled-back` (or `aborted` if nothing changed yet): what happened, what was
learned, what would have to be true to try again. A failed change recorded well is worth as
much as a successful one.

## Boundary with superpowers

- Code (a script, a stack, a migration tool) follows superpowers: spec, plan, implementation,
  with specs and plans where `.claude/rules/local.md` says. A plan that runs anything on a host
  ends with a deploy task that hands over to this skill, naming the change-record path.
- The change record lists that code's documents in `specs:` and `plans:` (checked by
  `wiki-lint`); the spec names the change record back.
- Deploying is one of superpowers' "stops" (outside the worktree): the user and this skill take
  over from there.

## References

- `references/situations.md`: path classification, creating and decommissioning, recording
  after the fact, changes with several units, and the red-flag table.
- `references/change-record-template.md`: the record to copy into `wiki/changes/`.
- `docs/proxmox-toolkit.md`: the Proxmox collectors and changing tools.
- The `llm-wiki` skill: capture, ingest, page formats, trust tiers.
