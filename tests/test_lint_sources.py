import tempfile
import unittest
from pathlib import Path

from tests.helpers import RAW_NODE, append, clean_wiki, codes, lint, write_files
from wikitools.util import short_hash

SOURCE = "sources/2026-06-01-node-status.md"


class LintSourcesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.wiki = clean_wiki(self.base)

    def tearDown(self):
        self.tmp.cleanup()

    def edit(self, rel, old, new):
        path = self.wiki / rel
        text = path.read_text()
        self.assertIn(old, text)
        path.write_text(text.replace(old, new))

    def link_page(self, rel, summary="x"):
        page = rel.removesuffix(".md")
        append(self.wiki / "index.md", f"- [[{page}]] — {summary}\n")
        append(self.wiki / "entities/host-pve1.md", f"\nSee [[{page}]].\n")

    def test_missing_required_field(self):
        self.edit(SOURCE, "trust_level: measured\n", "")
        found = [f for f in lint(self.wiki) if f.code == "E-SRC-FIELD"]
        self.assertEqual(len(found), 1)
        self.assertIn("trust_level", found[0].message)

    def test_invalid_field_values(self):
        cases = [("date: 2026-06-01", "date: 01/06/2026"),
                 ("type: measurement", "type: tweet"),
                 (f"source_hash: {short_hash(RAW_NODE)}", "source_hash: XYZ")]
        for old, new in cases:
            with self.subTest(new=new):
                wiki = clean_wiki(self.base / new.split(":")[0])
                path = wiki / SOURCE
                path.write_text(path.read_text().replace(old, new))
                self.assertIn(("E-SRC-FIELD", SOURCE), codes(lint(wiki)))

    def test_url_is_not_a_source_path(self):
        self.edit(SOURCE, "source: raw/2026-06-01-node-status.txt", "source: https://example.com/x")
        found = codes(lint(self.wiki))
        self.assertIn(("E-SRC-FIELD", SOURCE), found)
        self.assertIn(("W-RAW-UNCITED", "raw/2026-06-01-node-status.txt"), found)

    def test_missing_source_file(self):
        self.edit(SOURCE, "source: raw/2026-06-01-node-status.txt", "source: raw/nope.txt")
        self.assertIn(("E-SRC-MISSING", SOURCE), codes(lint(self.wiki)))

    def test_tampered_raw(self):
        append(self.wiki / "raw/2026-06-01-node-status.txt", "edited later\n")
        self.assertEqual(codes(lint(self.wiki)), [("E-RAW-HASH", SOURCE)])

    def test_repo_path_source(self):
        (self.base / ".git").mkdir()
        runbook = self.base / "docs" / "runbook.md"
        write_files(self.base, {"docs/runbook.md": "v1\n"})
        digest = short_hash(b"v1\n")  # no backslashes inside f-string expressions before 3.12
        write_files(self.wiki, {"sources/2026-06-02-runbook.md": f"""\
            ---
            title: Runbook
            date: 2026-06-02
            type: document
            source: docs/runbook.md
            source_hash: {digest}
            trust_level: internal-reviewed
            ---

            ## Summary

            Runbook for [[entities/host-pve1]].
            """})
        self.link_page("sources/2026-06-02-runbook.md")
        self.assertEqual(lint(self.wiki), [])
        runbook.write_text("v2\n")
        self.assertEqual(codes(lint(self.wiki)), [("W-REPO-HASH", "sources/2026-06-02-runbook.md")])

    def test_unknown_trust_and_extra_tier(self):
        self.edit(SOURCE, "trust_level: measured", "trust_level: rumor")
        self.assertEqual(codes(lint(self.wiki)), [("E-TRUST", SOURCE)])
        extra = clean_wiki(self.base / "extra", extra_trust="rumor")
        path = extra / SOURCE
        path.write_text(path.read_text().replace("trust_level: measured", "trust_level: rumor"))
        self.assertEqual(lint(extra), [])

    def test_stub_marker(self):
        append(self.wiki / SOURCE, "\nTODO(ingest)\n")
        self.assertEqual(codes(lint(self.wiki)), [("W-STUB", SOURCE)])

    def test_uncited_raw(self):
        write_files(self.wiki, {"raw/2026-06-02-extra.txt": "x\n"})
        self.assertEqual(codes(lint(self.wiki)), [("W-RAW-UNCITED", "raw/2026-06-02-extra.txt")])

    def test_markdown_in_raw_is_evidence_not_a_page(self):
        report = b"Agent report: see [[entities/ghost]].\n"
        write_files(self.wiki, {
            "raw/2026-06-02-report.md": report,
            "sources/2026-06-02-report.md": f"""\
                ---
                title: Agent report
                date: 2026-06-02
                type: report
                source: raw/2026-06-02-report.md
                source_hash: {short_hash(report)}
                trust_level: agent-report
                ---

                ## Summary

                Report about [[entities/host-pve1]].
                """,
        })
        self.link_page("sources/2026-06-02-report.md")
        self.assertEqual(lint(self.wiki), [])


if __name__ == "__main__":
    unittest.main()
