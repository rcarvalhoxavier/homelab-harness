import unittest

from tests import pvefixtures as fx
from tests.toolkit import Lab

# listsnapshot output of a container whose snapshots mention "current" in a description or a name;
# the first lacks the pseudo-entry row that ends every real listing
NO_CURRENT_ROW = {
    "description": "`-> before-fix    2026-06-01 10:00:00     the current state of the service\n",
    "name": "`-> pre-current-fix    2026-06-01 10:00:00     no-description\n",
}
WITH_CURRENT_ROW = {
    "description": NO_CURRENT_ROW["description"] + "    `-> current                                        You are here!\n",
    "name": NO_CURRENT_ROW["name"] + "    `-> current                                        You are here!\n",
}


class CurrentRowTest(unittest.TestCase):
    def setUp(self):
        self.lab = Lab()
        self.addCleanup(self.lab.close)
        fx.load(self.lab)

    def snapshot_volume_on_pve1(self):
        # a snapshot volume is what makes pve-capacity ask Proxmox for the snapshot list
        self.lab.responses["pve1"][fx.LVS_ALL]["stdout"] += "  snap_vm-101-disk-0_pre-current-fix pve 8589934592 41.20\n"

    def listing(self, text):
        self.lab.respond("pve1", "pct listsnapshot 101", stdout=text)

    def test_state_does_not_take_a_snapshot_for_the_current_row(self):
        for kind, text in NO_CURRENT_ROW.items():
            with self.subTest(kind=kind):
                self.listing(text)
                result = self.lab.run("pve-state", "101")
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn("no current line", result.stderr)

    def test_state_reads_a_listing_with_the_real_row(self):
        for kind, text in WITH_CURRENT_ROW.items():
            with self.subTest(kind=kind):
                self.listing(text)
                result = self.lab.run("pve-state", "101")
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_capacity_does_not_take_a_snapshot_for_the_current_row(self):
        for kind, text in NO_CURRENT_ROW.items():
            with self.subTest(kind=kind):
                self.snapshot_volume_on_pve1()
                self.listing(text)
                result = self.lab.run("pve-capacity", "--node", "pve1")
                self.assertEqual(result.returncode, 1)
                self.assertIn("could not read snapshots of ct 101 on pve1", result.stdout)

    def test_capacity_reads_a_listing_with_the_real_row(self):
        for kind, text in WITH_CURRENT_ROW.items():
            with self.subTest(kind=kind):
                self.snapshot_volume_on_pve1()
                self.listing(text)
                result = self.lab.run("pve-capacity", "--node", "pve1")
                self.assertNotIn("could not read snapshots of ct 101", result.stdout)

    def test_snapshot_name_check_does_not_take_a_snapshot_for_the_current_row(self):
        for kind, text in NO_CURRENT_ROW.items():
            with self.subTest(kind=kind):
                self.listing(text)
                result = self.lab.run("pve-snapshot", "101", "new-one", "--yes")
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn("cannot read the snapshots of ct 101", result.stdout + result.stderr)
                self.assertEqual(self.lab.commands("admin"), [])

    def test_snapshot_name_check_reads_a_listing_with_the_real_row(self):
        for kind, text in WITH_CURRENT_ROW.items():
            with self.subTest(kind=kind):
                self.listing(text)
                result = self.lab.run("pve-snapshot", "101", "new-one", "--dry-run")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("check: snapshot name new-one is unused: ok", result.stdout)


if __name__ == "__main__":
    unittest.main()
