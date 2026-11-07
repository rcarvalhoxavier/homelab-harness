import unittest

from wikitools import frontmatter
from wikitools.frontmatter import FrontmatterError


class FrontmatterTest(unittest.TestCase):
    def test_split(self):
        fm, body, line = frontmatter.split("---\na: 1\n---\n# T\n")
        self.assertEqual((fm, body, line), ("a: 1", "# T\n", 4))

    def test_no_frontmatter(self):
        self.assertEqual(frontmatter.split("# T\n"), (None, "# T\n", 1))

    def test_unterminated_frontmatter_is_absent(self):
        self.assertEqual(frontmatter.split("---\na: 1\n"), (None, "---\na: 1\n", 1))

    def test_parse_values(self):
        data = frontmatter.parse(
            'title: "A: b"\n'
            "count: 3\n"
            "flag: true\n"
            'tags: [a, "b c"]\n'
            "map: {secret: 0, ip: 2}\n"
            "url: https://x.test/a#frag\n"
            "mode: personal   # personal | team\n"
            "empty: []\n"
            "\n"
            "# a comment line\n"
            "blank:\n"
        )
        self.assertEqual(data, {
            "title": "A: b", "count": 3, "flag": True, "tags": ["a", "b c"],
            "map": {"secret": 0, "ip": 2}, "url": "https://x.test/a#frag",
            "mode": "personal", "empty": [], "blank": None,
        })

    def test_dates_stay_strings(self):
        self.assertEqual(frontmatter.parse("date: 2026-09-20\n"), {"date": "2026-09-20"})

    def test_errors_carry_file_line_numbers(self):
        with self.assertRaises(FrontmatterError) as cm:
            frontmatter.parse("ok: 1\nnot a pair\n")
        self.assertEqual(cm.exception.line, 3)
        with self.assertRaises(FrontmatterError):
            frontmatter.parse("a: 1\na: 2\n")
        with self.assertRaises(FrontmatterError):
            frontmatter.parse("a: [1, 2\n")
        with self.assertRaises(FrontmatterError):
            frontmatter.parse('a: "open\n')

    def test_dumps_roundtrip(self):
        data = {
            "title": "Pi-hole: after upgrade",
            "date": "2026-09-20",
            "source_hash": "3a545c13814c4282",
            "digits_hash": "1234567890123456",
            "origin": "pct config 110 @ pve1",
            "redactions": {"secret": 1, "ip": 0, "mac": 0},
            "targets": ["entities/a", "entities/b"],
        }
        text = frontmatter.dumps(data)
        self.assertTrue(text.startswith("---\n") and text.endswith("---\n"))
        fm, body, _ = frontmatter.split(text + "body\n")
        self.assertEqual(frontmatter.parse(fm), data)
        self.assertEqual(body, "body\n")


if __name__ == "__main__":
    unittest.main()
