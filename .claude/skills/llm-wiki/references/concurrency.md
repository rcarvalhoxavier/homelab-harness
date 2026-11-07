# Concurrency

A wiki that grows with several writers breaks in a specific way: two writers add the same fact
in different words, git merges both cleanly, and the wiki now says it twice, or contradicts
itself. Provenance (see `trust-and-provenance.md`) handles re-ingesting the same source; the
rules below handle writing at the same time.

## Personal mode with concurrent sessions

`mode: personal` means one human, but more than one agent session can write at once: one
session executing a change on the infrastructure while another ingests history, for example.
Then:

1. **One writer per target file.** Partition by subject: the session running a change owns the
   pages of that subject (its entities, concepts, sources and change record). Nobody edits a page
   another session owns; if a change is needed there, tell its owner.
2. **The shared files have a single writer.** `index.md`, `overview.md` and `log.md` are touched
   by every ingest, so they are where collisions are guaranteed. One session owns all three; the
   others send it the lines to add (an index line, a log entry, an overview paragraph) instead
   of editing. No merge resolved by an LLM.
3. **Announce the partition before writing**, and record it in `log.md` as an `update` entry.
   The partition is temporary: when the other session ends, the wiki goes back to one writer.

`raw/` never collides: every capture has its own file name, and nobody edits an existing one.

## Team mode

`mode: team` means several people and agents write the same wiki.

1. **Append-only, partitioned.** Each writer only adds content, in files or sections of their
   own. Additions to different lines commute, so git merges them without conflict.
2. **One writer per target at a time.** Partition by file or section instead of using locks.
3. **No LLM resolving merges.** For the rare collision on the same lines, use a deterministic
   rule (ordered append; last writer wins on structured fields). An LLM would reintroduce
   non-determinism.
4. **Real conflicts go to review.** A high-confidence update may apply; a reversed decision or a
   relevant contradiction goes to a human.
5. **Git is the transport.** One branch or worktree per writer where possible.
6. **Human review before use.** Content the agent generated counts as team knowledge only after
   a person reviewed it. Say so at the end of every ingest.
