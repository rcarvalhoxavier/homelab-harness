import re
import tempfile
import unittest
from pathlib import Path

from tests import ROOT
from tests.helpers import make_wiki
from wikitools.config import BASE_TRUST_LEVELS, ENTITY_KINDS, LOG_OPS, ConfigError, load_config


class ConfigTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def edit(self, wiki, old, new):
        path = wiki / "AGENTS.md"
        text = path.read_text()
        self.assertIn(old, text)
        path.write_text(text.replace(old, new))

    def test_valid(self):
        cfg = load_config(make_wiki(self.base))
        self.assertEqual((cfg.mode, cfg.exposure, cfg.language, cfg.stale_after_days,
                          cfg.pending_after_days), ("personal", "private", "en", 90, 14))
        self.assertEqual(cfg.trust_levels, BASE_TRUST_LEVELS)
        self.assertEqual(cfg.entity_kinds, ENTITY_KINDS)

    def test_extras(self):
        cfg = load_config(make_wiki(self.base, extra_trust="vendor-forum", extra_kinds="appliance"))
        self.assertIn("vendor-forum", cfg.trust_levels)
        self.assertIn("appliance", cfg.entity_kinds)

    def test_missing_file_points_to_init(self):
        with self.assertRaisesRegex(ConfigError, "bin/init"):
            load_config(self.base / "nowhere")

    def test_no_frontmatter(self):
        wiki = self.base / "wiki"
        wiki.mkdir()
        (wiki / "AGENTS.md").write_text("# schema\n")
        with self.assertRaisesRegex(ConfigError, "frontmatter"):
            load_config(wiki)

    def test_bad_values(self):
        cases = [
            ("exposure: private", "exposure: open", "exposure"),
            ("mode: personal", "mode: solo", "mode"),
            ("stale_after_days: 90", "stale_after_days: 0", "stale_after_days"),
            ("harness_schema: 1", "harness_schema: 2", "harness_schema"),
            ("language: en", "language: ", "language"),
        ]
        for old, new, word in cases:
            with self.subTest(word=word):
                wiki = make_wiki(self.base / word)
                self.edit(wiki, old, new)
                with self.assertRaisesRegex(ConfigError, word):
                    load_config(wiki)

    def test_exposure_is_required(self):
        wiki = make_wiki(self.base)
        self.edit(wiki, "exposure: private\n", "")
        with self.assertRaisesRegex(ConfigError, "exposure"):
            load_config(wiki)

    def test_extra_names_cannot_shadow_builtins(self):
        with self.assertRaisesRegex(ConfigError, "built-in"):
            load_config(make_wiki(self.base, extra_trust="measured"))

    def test_frontmatter_error_keeps_line(self):
        wiki = make_wiki(self.base)
        self.edit(wiki, "language: en", "language en")
        with self.assertRaises(ConfigError) as cm:
            load_config(wiki)
        self.assertEqual(cm.exception.line, 5)


class LogOpsDocsTest(unittest.TestCase):
    def test_every_logged_op_is_valid(self):
        text = (ROOT / ".claude/skills/llm-wiki/references/operations.md").read_text()
        logged = set(re.findall(r"## \[YYYY-MM-DD\] (\w+) \|", text))
        self.assertIn("reconcile", logged)
        self.assertEqual(logged - set(LOG_OPS), set())

    def test_documented_op_lists_match(self):
        for name in (".claude/skills/llm-wiki/references/page-formats.md", "templates/wiki/log.md"):
            with self.subTest(name):
                text = " ".join((ROOT / name).read_text().split())
                listed = re.search(r"op is one of (.*?)\.", text).group(1)
                self.assertEqual(re.findall(r"`(\w+)`", listed), list(LOG_OPS))


if __name__ == "__main__":
    unittest.main()
