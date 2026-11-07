import tempfile
import unittest
from pathlib import Path

from tests.helpers import RAW_NODE, append, clean_wiki, codes, lint, write_files
from wikitools.util import short_hash

ENTITY = "entities/host-pve1.md"
CHANGE = "changes/2026-06-01-upgrade-pve1.md"
CHANGE_TEXT = """\
    ---
    date: 2026-06-01
    targets: [entities/host-pve1]
    outcome: done
    rollback: snapshot
    baseline: sources/2026-06-01-node-status
    after: sources/2026-06-01-node-status
    ---

    # Upgrade pve1

    ## Pending

    - [x] Confirm the node rebooted — owner: user
    - [ ] Remove snapshot pre-upgrade — owner: user
    """


class LintPagesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.wiki = clean_wiki(self.base)

    def tearDown(self):
        self.tmp.cleanup()

    def edit(self, rel, old, new, wiki=None):
        path = (wiki or self.wiki) / rel
        text = path.read_text()
        self.assertIn(old, text)
        path.write_text(text.replace(old, new))

    def add_change(self):
        write_files(self.wiki, {CHANGE: CHANGE_TEXT})
        append(self.wiki / "index.md", "- [[changes/2026-06-01-upgrade-pve1]] — upgrade\n")
        append(self.wiki / ENTITY, "\n## Update history\n\n- 2026-06-01: [[changes/2026-06-01-upgrade-pve1]]\n")

    # entities

    def test_entity_kind_and_extra_kinds(self):
        self.edit(ENTITY, "kind: host", "kind: server")
        self.assertEqual(codes(lint(self.wiki)), [("E-ENTITY-FIELD", ENTITY)])
        extra = clean_wiki(self.base / "extra", extra_kinds="appliance")
        self.edit(ENTITY, "kind: host", "kind: appliance", wiki=extra)
        self.assertEqual(lint(extra), [])

    def test_entity_status_and_missing_frontmatter(self):
        self.edit(ENTITY, "status: active", "status: alive")
        self.assertEqual(codes(lint(self.wiki)), [("E-ENTITY-FIELD", ENTITY)])
        write_files(self.wiki, {ENTITY: "# host-pve1\n\nNode [[sources/2026-06-01-node-status]].\n"})
        self.assertEqual(codes(lint(self.wiki)), [("E-ENTITY-FIELD", ENTITY)])

    def test_last_verified_format_and_staleness(self):
        self.assertEqual(lint(self.wiki, today="2026-08-30"), [])
        found = lint(self.wiki, today="2026-12-01")
        self.assertEqual(codes(found), [("W-STALE", ENTITY)])
        self.assertEqual(found[0].line, 4)
        self.edit(ENTITY, "last_verified: 2026-06-01", "last_verified: yesterday")
        self.assertEqual(codes(lint(self.wiki)), [("E-ENTITY-FIELD", ENTITY)])

    # change records

    def test_valid_change_within_limit(self):
        self.add_change()
        self.assertEqual(lint(self.wiki, today="2026-06-10"), [])

    def test_open_pending_after_limit(self):
        self.add_change()
        found = lint(self.wiki, today="2026-07-01")
        self.assertEqual(codes(found), [("W-PENDING", CHANGE)])
        self.assertEqual(found[0].line, 15)
        self.assertIn("Remove snapshot", found[0].message)

    def test_pending_message_keeps_inline_code(self):
        self.add_change()
        self.edit(CHANGE, "Remove snapshot pre-upgrade", "Remove snapshot `pre-upgrade`")
        found = lint(self.wiki, today="2026-07-01")
        self.assertIn("Remove snapshot `pre-upgrade` — owner: user", found[0].message)

    def test_checked_items_do_not_warn(self):
        self.add_change()
        self.edit(CHANGE, "- [ ] Remove", "- [x] Remove")
        self.assertEqual(lint(self.wiki, today="2026-07-01"), [])

    def test_invalid_change_fields(self):
        cases = [("outcome: done", "outcome: maybe"),
                 ("rollback: snapshot", "rollback: prayer"),
                 ("targets: [entities/host-pve1]", "targets: []"),
                 ("targets: [entities/host-pve1]", "targets: [entities/ghost]"),
                 ("after: sources/2026-06-01-node-status", "after: sources/ghost"),
                 ("after: sources/2026-06-01-node-status\n", ""),
                 ("date: 2026-06-01", "date: June")]
        for old, new in cases:
            with self.subTest(new=new):
                self.add_change()
                self.edit(CHANGE, old, new)
                self.assertIn(("E-CHANGE-FIELD", CHANGE), codes(lint(self.wiki, today="2026-06-10")))
                write_files(self.wiki, {CHANGE: CHANGE_TEXT})

    def test_planned_too_long(self):
        self.add_change()
        self.edit(CHANGE, "outcome: done", "outcome: planned")
        self.edit(CHANGE, "after: sources/2026-06-01-node-status\n", "")
        found = codes(lint(self.wiki, today="2026-07-01"))
        self.assertIn(("W-PLANNED", CHANGE), found)
        self.assertNotIn(("E-CHANGE-FIELD", CHANGE), found)

    def test_frontmatter_refs_count_as_inbound(self):
        self.add_change()
        after_raw = RAW_NODE + b"after\n"
        write_files(self.wiki, {
            "raw/2026-06-02-after.txt": after_raw,
            "sources/2026-06-02-after.md": f"""\
                ---
                title: After
                date: 2026-06-02
                type: measurement
                source: raw/2026-06-02-after.txt
                source_hash: {short_hash(after_raw)}
                trust_level: measured
                ---

                ## Summary

                After state of [[entities/host-pve1]].
                """,
        })
        append(self.wiki / "index.md", "- [[sources/2026-06-02-after]] — after\n")
        self.edit(CHANGE, "after: sources/2026-06-01-node-status", "after: sources/2026-06-02-after")
        self.assertEqual(lint(self.wiki, today="2026-06-10"), [])

    # contradictions and citations

    def test_contradiction_heading(self):
        append(self.wiki / ENTITY, "\n## ⚠️ Contradiction\n\nA says 8.4.1 [[sources/2026-06-01-node-status]].\n")
        self.assertEqual(codes(lint(self.wiki)), [("W-CONTRADICTION", ENTITY)])

    def test_notes_and_contradictions_heading_is_not_a_contradiction(self):
        append(self.wiki / ENTITY, "\n## Notes and contradictions\n\nNone.\n")
        self.assertEqual(lint(self.wiki), [])

    def test_uncited_paragraph(self):
        append(self.wiki / ENTITY, "\nThis node also hosts the media stack and it has been running "
                                   "without issues for months.\n")
        found = lint(self.wiki)
        self.assertEqual([(f.level, f.code, f.path, f.line) for f in found],
                         [("INFO", "I-UNCITED", ENTITY, 11)])

    def test_cited_or_short_paragraphs_pass(self):
        append(self.wiki / ENTITY, "\nThis node also hosts the media stack and it has been running "
                                   "without issues [[sources/2026-06-01-node-status]].\n"
                                   "\nShort note about the node with exactly eleven words right here.\n")
        self.assertEqual(lint(self.wiki), [])


if __name__ == "__main__":
    unittest.main()
