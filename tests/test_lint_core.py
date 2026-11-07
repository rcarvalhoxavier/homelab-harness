import tempfile
import unittest
from pathlib import Path

from tests.helpers import append, clean_wiki, codes, lint, run_bin, write_files


class LintCoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.wiki = clean_wiki(self.base)

    def tearDown(self):
        self.tmp.cleanup()

    def test_clean_wiki_has_no_findings(self):
        self.assertEqual(lint(self.wiki), [])

    def test_config_error(self):
        agents = self.wiki / "AGENTS.md"
        agents.write_text(agents.read_text().replace("exposure: private", "exposure: open"))
        self.assertIn(("E-CONFIG", "AGENTS.md"), codes(lint(self.wiki)))

    def test_bad_capture_patterns(self):
        (self.wiki / ".capture-patterns").write_text("# ok\n([unclosed\n")
        found = [f for f in lint(self.wiki) if f.code == "E-CONFIG"]
        self.assertEqual([(f.path, f.line) for f in found], [(".capture-patterns", 2)])

    def test_broken_link(self):
        append(self.wiki / "overview.md", "\nSee [[entities/ghost]].\n")
        found = lint(self.wiki)
        self.assertEqual(codes(found), [("E-LINK", "overview.md")])
        self.assertEqual(found[0].line, 5)

    def test_links_in_code_are_ignored(self):
        append(self.wiki / "overview.md",
               '\n```bash\nif [[ -n "$x" ]]; then echo; fi\n```\n\nInline `[[ -z $y ]]` too.\n')
        self.assertEqual(lint(self.wiki), [])

    def test_orphan_page(self):
        write_files(self.wiki, {"concepts/lonely.md": "# Lonely\n"})
        append(self.wiki / "index.md", "- [[concepts/lonely]] — lonely\n")
        self.assertEqual(codes(lint(self.wiki)), [("W-ORPHAN", "concepts/lonely.md")])

    def test_links_from_log_do_not_count_as_inbound(self):
        write_files(self.wiki, {"concepts/logged.md": "# Logged\n"})
        append(self.wiki / "index.md", "- [[concepts/logged]] — logged\n")
        append(self.wiki / "log.md", "\nMentioned [[concepts/logged]].\n")
        self.assertEqual(codes(lint(self.wiki)), [("W-ORPHAN", "concepts/logged.md")])

    def test_page_missing_from_index(self):
        write_files(self.wiki, {"concepts/unindexed.md": "# Unindexed\n"})
        append(self.wiki / "overview.md", "\nSee [[concepts/unindexed]].\n")
        self.assertEqual(codes(lint(self.wiki)), [("W-INDEX", "concepts/unindexed.md")])

    def test_bad_log_heading(self):
        append(self.wiki / "log.md", "## 2026-06-02 ingest - no brackets\n")
        found = lint(self.wiki)
        self.assertEqual(codes(found), [("W-LOG", "log.md")])
        self.assertEqual(found[0].line, 4)

    def test_reconcile_log_heading(self):
        append(self.wiki / "log.md", "\n## [2026-06-02] reconcile | First reconciliation\n")
        self.assertEqual(codes(lint(self.wiki)), [])

    def run_cli(self, *args):
        elsewhere = self.base / "elsewhere"
        elsewhere.mkdir(exist_ok=True)
        return run_bin("wiki-lint", "--wiki", self.wiki, "--today", "2026-07-01",
                       "--env-file", self.base / "none", *args, cwd=elsewhere)

    def test_cli_clean_and_broken(self):
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.strip().splitlines()[-1],
                         "wiki-lint: 0 error(s), 0 warning(s), 0 info")
        append(self.wiki / "overview.md", "\nSee [[entities/ghost]].\n")
        result = self.run_cli()
        self.assertEqual(result.returncode, 1)
        self.assertIn(f"ERROR {self.wiki.as_posix()}/overview.md:5 E-LINK [[entities/ghost]] does not exist",
                      result.stdout)

    def test_cli_usage_errors(self):
        self.assertEqual(run_bin("wiki-lint", "--wiki", self.wiki, "--today", "2026-13-01").returncode, 2)
        self.assertEqual(run_bin("wiki-lint", "--wiki", self.base / "nowiki").returncode, 2)


if __name__ == "__main__":
    unittest.main()
