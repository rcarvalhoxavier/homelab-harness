import tempfile
import unittest
from pathlib import Path

from wikitools.util import SLUG_RE, harness_root, parse_date, repo_root_for, short_hash


class UtilTest(unittest.TestCase):
    def test_short_hash_is_first_16_hex_of_sha256(self):
        self.assertEqual(short_hash(b"abc"), "ba7816bf8f01cfea")

    def test_slug(self):
        for ok in ("a", "pve1-versions", "ct-101-pihole"):
            self.assertTrue(SLUG_RE.match(ok), ok)
        for bad in ("", "Bad", "a_b", "-a", "a-", "a--b", "a b"):
            self.assertFalse(SLUG_RE.match(bad), bad)

    def test_parse_date_is_strict(self):
        self.assertEqual(str(parse_date("2026-09-29")), "2026-09-29")
        for bad in ("2026-9-29", "20260929", "2026-02-30", 20260929, None):
            self.assertIsNone(parse_date(bad), bad)

    def test_harness_root_holds_lib(self):
        self.assertTrue((harness_root() / "lib" / "wikitools" / "util.py").is_file())

    def test_repo_root_for(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            (base / "repo" / ".git").mkdir(parents=True)
            (base / "repo" / "wiki").mkdir()
            self.assertEqual(repo_root_for(base / "repo" / "wiki"), base / "repo")
            (base / "loose" / "wiki").mkdir(parents=True)
            self.assertEqual(repo_root_for(base / "loose" / "wiki"), base / "loose")


if __name__ == "__main__":
    unittest.main()
