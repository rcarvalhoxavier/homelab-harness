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


class BindMountTest(unittest.TestCase):
    """Proxmox refuses to snapshot a container with a mount point that is not a storage volume."""

    def setUp(self):
        self.lab = Lab()
        self.addCleanup(self.lab.close)
        fx.load(self.lab)

    def with_mount_point(self, line):
        self.lab.respond("pve1", "pct config 101", stdout=fx.CONFIGS["101"] + line)

    def test_a_bind_mount_or_a_device_mount_blocks_the_snapshot(self):
        for line, path in (("mp0: /mnt/data,mp=/data\n", "/mnt/data"),
                           ("mp1: /dev/sdb1,mp=/data\n", "/dev/sdb1")):
            with self.subTest(line=line):
                self.with_mount_point(line)
                result = self.lab.run("pve-snapshot", "101", "before-x", "--yes")
                self.assertEqual(result.returncode, 1, result.stdout)
                key = line.split(":")[0]
                self.assertIn(f"check: {key} of ct 101 mounts the host path {path}, "
                              "which Proxmox cannot snapshot: FAILED\n", result.stdout)
                self.assertEqual(self.lab.commands("admin"), [])

    def test_the_same_check_stops_a_snapshot_before_an_update(self):
        self.with_mount_point("mp0: /mnt/data,mp=/data\n")
        result = self.lab.run("pve-update-ct", "101", "--snapshot", "--dry-run")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("mp0 of ct 101", result.stdout + result.stderr)
        self.assertEqual(self.lab.commands("admin"), [])

    def test_a_mount_point_on_a_storage_volume_passes(self):
        self.with_mount_point("mp0: local-lvm:vm-101-disk-1,mp=/data,size=8G\n")
        result = self.lab.run("pve-snapshot", "101", "before-x", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("check: every disk of ct 101 supports snapshots: ok", result.stdout)

    def test_a_container_with_only_a_rootfs_passes(self):
        result = self.lab.run("pve-snapshot", "101", "before-x", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
