# Trust and provenance

## Trust tiers

| trust_level | What it is | Strength |
|---|---|---|
| `measured` | Output of a command run against the real system: `pct config`, an API response, a log line | **Strongest for state** ("the version is X"): the system itself speaking |
| `internal-reviewed` | A doc in this repo that a human reviewed: spec, runbook, design notes | Strong, and the authority for intent and causes |
| `vendor` | Official documentation or changelog of the software or hardware | Medium-high |
| `third-party` | Code or docs from third parties: script collections, reputable blogs | Medium |
| `user` | The admin's statement about their own setup | Authority on intent and composition; **not** on current state (see below) |
| `agent-report` | Another agent session's account of what it observed | Medium-low: second hand (see below) |
| `web` | Forums, threads, the random web | Low |

A claim is only as strong as the weakest tier among its sources. `measured` beats everything for
facts of **state**, but not for intent or cause ("we upgraded because…"): for those,
`internal-reviewed` and `user` are the authority.

A local tier goes into `extra_trust_levels` in `wiki/AGENTS.md`, with a description and its rank
in the "Extra trust tiers" section there.

## The `user` rule

The admin is the authority on **what they wanted**, **what they set up** and **why**. No
measurement recovers intent. But memory ages: "it is configured with X" may describe how things
were a year ago. So:

1. Record the statement as it was said, with the date it was said:
   `bin/wiki-capture <slug> --file notes.txt --trust user --type conversation`.
2. Verify whatever can be verified (a port open, a process running, a file present) with a
   capture. What passes is stated from the new `measured` source.
3. Never contradict the user without evidence. If a measurement disagrees, record both and ask:
   the measurement may be looking in the wrong place.

At the point of use, say where an unverified claim comes from: "per the admin (tier `user`)".

## The `agent-report` rule

A report from another agent session is second hand, even when it describes a measurement: the
original output did not come with it, the account may have simplified it, and the session that
saw it may be gone. Three obligations:

1. Store the report verbatim before deriving anything from it:
   `bin/wiki-capture <slug> --file report.md --trust agent-report --type report`.
2. Verify independently whatever can still be verified. A claim confirmed by a new capture is
   stated from that `measured` source.
3. Mark what can no longer be verified, such as state the reported work itself destroyed (the
   old version of a package, a transient error), as unverifiable **at the point of use**, not
   only in the frontmatter.

A report that survives verification is valuable: it often holds exactly what no document
records, because nobody else was there.

## Promotion to `measured`

A claim is promoted by citing the capture that confirmed it, next to or instead of the weaker
source: "port 8123 answers [[sources/2026-06-02-rpi-ports]] (first reported by the admin,
[[sources/2026-06-01-admin-notes]])".

## Hashes and idempotency

- `source_hash` is the first 16 hexadecimal characters of the sha256 of the evidence file.
  `bin/wiki-capture` writes it; by hand: `sha256sum <file> | cut -c1-16`.
- The same evidence captured twice has the same hash, and `bin/wiki-capture` answers
  `unchanged:` instead of writing a copy (it writes a dated source page for the new observation
  instead). Ingesting in any order converges to the same wiki.
- Claim identity is the citation plus the fact's identifier (host, guest id, version), not its
  wording. Grep for those before you write.
- `E-RAW-HASH`: a raw file changed. That is never legitimate; restore it from git.
- `W-REPO-HASH`: a versioned repo file cited as a source changed. Reingest it: update the source
  page and its hash, and re-evaluate every claim derived from it.

## State change vs contradiction

A state change is two sources describing **different moments**: "`5.15.20.20` on 2026-09-19"
and "`6.3.0.45` on 2026-09-20". The page states the current value and its `## Update history`
keeps the old one with its source. Nothing is lost and nothing is contradictory.

A contradiction is two sources disagreeing about **the same moment**. Add a
`## ⚠️ Contradiction` section with both versions, their dates and sources, and ask the user.
Never pick one silently. Once it is resolved, keep the losing version in the update history with
the reason it lost.

## Dates and versions

Always absolute dates (`2026-09-20`), never "last week". Always complete versions (`6.3.0.45`),
never "version 6" or "the latest".

## `last_verified`

The date of the most recent `measured` source that confirmed the page's state claims. A `user`
or `agent-report` source never bumps it. `W-STALE` fires when it is older than
`stale_after_days`; re-verify with a capture (see `operations.md`).
