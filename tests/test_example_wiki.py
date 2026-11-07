import unittest

from tests import ROOT
from tests.helpers import codes, lint

EXAMPLE = ROOT / "examples" / "wiki"


class ExampleWikiTest(unittest.TestCase):
    def test_only_demonstration_findings(self):
        self.assertEqual(sorted(codes(lint(EXAMPLE, today="2026-07-01"))), [
            ("W-PENDING", "changes/2026-06-14-pihole-v6-upgrade.md"),
            ("W-STALE", "entities/home-assistant.md"),
            ("W-STALE", "entities/host-rpi.md"),
        ])

    def test_every_page_type_is_present(self):
        for name in ("entities", "concepts", "sources", "changes", "analyses", "raw"):
            self.assertTrue(any((EXAMPLE / name).iterdir()), name)


if __name__ == "__main__":
    unittest.main()
