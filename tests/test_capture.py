import io
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

from tests.helpers import make_wiki, run_bin
from wikitools import capture, frontmatter
from wikitools.util import short_hash


class CaptureTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.wiki = make_wiki(self.base)
        self.env = self.base / ".env.local"

    def tearDown(self):
        self.tmp.cleanup()

    def cap(self, *args, stdin=None, cwd=None, wiki=None):
        return run_bin("wiki-capture", *args, "--wiki", wiki or self.wiki, "--env-file", self.env,
                       stdin=stdin, cwd=cwd or self.base)

    def raw_files(self):
        return sorted(p.name for p in (self.wiki / "raw").glob("*") if p.is_file())

    def test_writes_redacted_raw_and_source_stub(self):
        result = self.cap("node-status", "--date", "2026-06-01", "--origin", "pveversion @ pve1",
                          stdin="pve-manager/8.4.1\npassword=hunter22\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        raw = self.wiki / "raw" / "2026-06-01-node-status.txt"
        self.assertEqual(raw.read_text(), "pve-manager/8.4.1\npassword=<REDACTED:secret>\n")
        source = self.wiki / "sources" / "2026-06-01-node-status.md"
        fm, body, _ = frontmatter.split(source.read_text())
        meta = frontmatter.parse(fm)
        self.assertEqual(meta, {
            "title": "Node status", "date": "2026-06-01", "type": "measurement",
            "source": "raw/2026-06-01-node-status.txt", "source_hash": short_hash(raw.read_bytes()),
            "trust_level": "measured", "origin": "pveversion @ pve1",
            "redactions": {"secret": 1, "ip": 0, "mac": 0, "host": 0},
        })
        self.assertIn("TODO(ingest)", body)
        self.assertIn(f"hash: {meta['source_hash']}", result.stdout)

    def test_identical_content_is_unchanged(self):
        # No second raw file; a dated source records the re-verification.
        self.cap("node-status", "--date", "2026-06-01", stdin="same\n")
        result = self.cap("node-recheck", "--date", "2026-06-30", stdin="same\n")
        self.assertEqual(result.returncode, 0)
        self.assertTrue(result.stdout.startswith("unchanged: "))
        self.assertIn("last_verified", result.stdout)
        self.assertEqual(self.raw_files(), ["2026-06-01-node-status.txt"])
        self.assertIn("source: raw/2026-06-01-node-status.txt",
                      (self.wiki / "sources" / "2026-06-30-node-recheck.md").read_text())

    def test_raw_is_immutable(self):
        self.cap("node-status", "--date", "2026-06-01", stdin="first\n")
        result = self.cap("node-status", "--date", "2026-06-01", stdin="second\n")
        self.assertEqual(result.returncode, 2)
        self.assertIn("immutable", result.stderr)
        self.assertEqual((self.wiki / "raw" / "2026-06-01-node-status.txt").read_text(), "first\n")

    def test_dry_run_writes_nothing(self):
        result = self.cap("x", "--dry-run", stdin="token=abcdef123456\n")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout,
                         "token=<REDACTED:secret>\n--- redactions: secret=1 ip=0 mac=0 host=0\n")
        self.assertFalse((self.wiki / "raw").exists())

    def test_empty_input(self):
        self.assertEqual(self.cap("x", stdin="  \n").returncode, 3)

    def test_usage_errors(self):
        self.assertEqual(self.cap("Bad_Slug", stdin="x\n").returncode, 1)
        self.assertEqual(self.cap("x", "--trust", "rumor", stdin="x\n").returncode, 1)
        self.assertEqual(self.cap("x", "--type", "tweet", stdin="x\n").returncode, 1)
        self.assertEqual(self.cap("x", "--date", "2026-13-01", stdin="x\n").returncode, 1)
        self.assertEqual(self.cap("x", "--bogus", stdin="x\n").returncode, 1)
        missing = self.cap("x", stdin="x\n", wiki=self.base / "nowiki")
        self.assertEqual(missing.returncode, 1)
        self.assertIn("bin/init", missing.stderr)

    def test_tty_without_file_is_usage_error(self):
        class Tty(io.StringIO):
            def isatty(self):
                return True
        err = io.StringIO()
        with mock.patch("sys.stdin", Tty("")), redirect_stderr(err):
            code = capture.main(["x", "--wiki", str(self.wiki), "--env-file", str(self.env)])
        self.assertEqual(code, 1)
        self.assertIn("pipe", err.getvalue())

    def test_file_with_crlf_and_invalid_utf8(self):
        data = self.base / "router-export.txt"
        data.write_bytes(b"line1\r\nbad \xff byte\r\n")
        result = self.cap("router-export", "--date", "2026-06-02", "--file", data)
        self.assertEqual(result.returncode, 0, result.stderr)
        raw = self.wiki / "raw" / "2026-06-02-router-export.txt"
        # Not UTF-8, so decoded as cp1252: \xff is "ÿ", not a lost byte.
        self.assertEqual(raw.read_bytes(), b"line1\r\nbad \xc3\xbf byte\r\n")
        fm, _, _ = frontmatter.split((self.wiki / "sources" / "2026-06-02-router-export.md").read_text())
        self.assertEqual(frontmatter.parse(fm)["source_hash"], short_hash(raw.read_bytes()))

    def test_public_exposure_redacts_addresses(self):
        public = make_wiki(self.base / "pub", exposure="public")
        result = self.cap("gw", "--date", "2026-06-01", stdin="gw 10.0.0.1\n", wiki=public)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((public / "raw" / "2026-06-01-gw.txt").read_text(), "gw <IP-1>\n")

    def test_env_literals_are_redacted(self):
        self.env.write_text("PVE_ROOT_PASSWORD=Tr0ub4dor&3\n")
        self.cap("login", "--date", "2026-06-01", stdin="echo Tr0ub4dor&3\n")
        self.assertEqual((self.wiki / "raw" / "2026-06-01-login.txt").read_text(),
                         "echo <REDACTED:secret>\n")

    def test_invalid_custom_patterns(self):
        (self.wiki / ".capture-patterns").write_text("([unclosed\n")
        result = self.cap("x", stdin="x\n")
        self.assertEqual(result.returncode, 1)
        self.assertIn(".capture-patterns", result.stderr)

    def test_runs_from_any_directory(self):
        elsewhere = self.base / "elsewhere"
        elsewhere.mkdir()
        result = self.cap("x", "--date", "2026-06-01", stdin="x\n", cwd=elsewhere)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_origin_and_title_are_redacted(self):
        result = self.cap("nas-api", "--date", "2026-06-01",
                          "--origin", "curl -H 'Authorization: Bearer abcdefgh12345678' @ nas",
                          "--title", "NAS API with password=Hunter2x",
                          stdin="ok\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        text = (self.wiki / "sources" / "2026-06-01-nas-api.md").read_text()
        self.assertNotIn("abcdefgh12345678", text)
        self.assertNotIn("Hunter2x", text)
        meta = frontmatter.parse(frontmatter.split(text)[0])
        self.assertEqual(meta["redactions"], {"secret": 2, "ip": 0, "mac": 0, "host": 0})


if __name__ == "__main__":
    unittest.main()
