# Situations

Details for the cases the main flow in `SKILL.md` only names.

## Classifying the path

| Path | When | What changes in the flow |
|---|---|---|
| **Trivial** | One reversible step with no data at risk: restart a service, toggle a setting you can toggle back | Short plan and record. The baseline and after still run; they take seconds. No simulation |
| **Standard** | Everything else | The full flow in `SKILL.md` |
| **Risky** | Irreversible or hard to reverse; affects several hosts or the whole cluster; touches storage, quorum, backups, or the network path the admin uses to reach the hosts | Full flow, plus a written plan in the change record before approval, a fresh reviewer (a subagent, when available) on the plan, and a simulation even when a rollback exists |

The ratchet: when a trivial or standard change turns out to hide more (an unexpected dependency,
a storage that cannot snapshot, a version jump bigger than planned), stop and upgrade the path.
Nothing downgrades mid-change.

## Creating something new

A new container, VM, service or port forward has no entity page and no state to baseline yet.

1. Create the target's entity page first, `status: evaluating`, with what is planned (host,
   storage, ports), so the change record can list it in `targets`.
2. The baseline is the state of what hosts it: free capacity, used IDs, ports in use, firewall
   rules (`pvesm status`, `pct list`, `ss -tlnp`).
3. The rollback is usually "destroy the new guest", or "remove the rule": name it and confirm
   it would work (nothing else depends on the new thing yet).
4. The done-criteria are functional: the service answers, the port is reachable from where it
   should be and not from where it should not.
5. On success, set the entity to `status: active` and add it to the inventory.

## Decommissioning

1. The baseline shows what still depends on the target (DNS records, backups, proxies, other
   guests' configs); grep the wiki for its page's inbound links.
2. The rollback is a verified backup (restorable), taken and checked before anything is removed.
3. The done-criteria include the dependencies gone or repointed.
4. On success, set the entity to `status: retired` (keep the page and its history), remove it
   from the inventory, and fix the pages that linked to it as current.

## Recording a change after the fact

When the user already made the change (or it happened before the wiki existed):

1. Capture the current state as the `after`.
2. If an earlier capture shows the state before, cite it as `baseline:`. Otherwise set
   `baseline_unavailable: <reason>` in the frontmatter; `wiki-lint` accepts that instead of a
   baseline for `done` and `rolled-back`.
3. Execution comes from the user (tier `user`) or from logs (captured); say which at the point
   of use. The Diff is partial: say what cannot be compared.
4. Do not invent a baseline, and do not present the record as if it had been planned.

## Changes with several units

A rolling upgrade of two nodes, a Pi-hole pair or several guests is several reversible units
with an order between them:

1. One change record per unit, each with its own rollback, baseline and after.
2. A parent record (`targets` = all of them) with the order, the stop rule between units ("the
   first unit's done-criteria all hold, and nothing in its after-capture is unexpected"), and
   links to the children in Links.
3. Never start the next unit while the previous one is not `done`.

## Red flags

| Thought | Reality |
|---|---|
| "It's just a restart, no baseline" | Capture anyway: it takes seconds and it is the evidence |
| "The snapshot exists, I saw it earlier" | Confirm it now, and cite the capture that shows it |
| "The backup job ran last night, that is the rollback" | A backup you have not proved restorable is a hope |
| "The user said go ahead" | That approved the plan, not the next destructive command |
| "The after looks fine, skip the diff" | The diff is the record; quote the done-criteria |
| "I will write the Execution section at the end" | After an interruption nobody will know what ran |
| "The command failed, I'll just run it again" | Re-capture the state first: it may have half-applied |
| "It is only a small change, no record" | Small undocumented changes are what the next incident traces back to |
