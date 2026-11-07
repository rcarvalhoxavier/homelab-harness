import os
import unittest

from tests import ROOT
from tests import pvefixtures as fx


@unittest.skipUnless(os.environ.get("HARNESS_ACCEPTANCE") == "1", "acceptance gate: fixtures compared with a real node")
class FixtureOriginTest(unittest.TestCase):
    def test_every_fixture_set_was_verified_or_is_declared_experimental(self):
        self.assertTrue(fx.ORIGIN["8"].startswith("pve-manager/8."), fx.ORIGIN["8"])
        self.assertEqual({v: o for v, o in fx.ORIGIN.items()
                          if not o.startswith(("pve-manager/", "experimental"))}, {})


class ExperimentalVersionsTest(unittest.TestCase):
    def test_an_experimental_version_is_declared_where_users_read(self):
        for version, origin in fx.ORIGIN.items():
            if not origin.startswith("experimental"):
                continue
            with self.subTest(version=version):
                for doc in ("README.md", "docs/proxmox-toolkit.md"):
                    self.assertIn(f"Proxmox VE {version} support is experimental",
                                  (ROOT / doc).read_text(encoding="utf-8"), doc)
