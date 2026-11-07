import unittest

from tests import pvefixtures as fx
from tests.toolkit import Lab


class SnapshotTest(unittest.TestCase):
    def setUp(self):
        self.lab = Lab()
        self.addCleanup(self.lab.close)
        fx.load(self.lab)

    def test_dry_run(self):
        result = self.lab.run("pve-snapshot", "101", "before-x", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout,
                         "check: ct 101 is on pve1: ok\n"
                         "check: snapshot name before-x is unused: ok\n"
                         "check: every disk of ct 101 supports snapshots: ok\n"
                         "target: ct 101 on pve1\npath: trivial\n"
                         "rollback: pct rollback 101 before-x; remove it later with pct delsnapshot 101 before-x\n"
                         "baseline/after: bin/pve-state 101\n"
                         "step 1/1: ssh pve1-admin -- pct snapshot 101 before-x\n"
                         "dry run: nothing was changed\n")
        self.assertEqual(self.lab.commands("admin"), [])

    def duplicate_101(self):
        self.lab.respond("pve2", "pct list", stdout=fx.pct_list([("101", "running", "pihole"),
                                                                 ("102", "running", "pihole")]))
        for command in ("pct config 101", "pct listsnapshot 101"):
            self.lab.respond("pve2", command, **self.lab.responses["pve1"][command])

    def test_an_unreadable_independent_node_needs_node(self):
        # pve1 is standalone and pve2 is down: pve2 may hold another CT 101
        self.lab.respond("pve1", "cat /etc/pve/corosync.conf", exit=1)
        self.lab.respond("pve1", "ls /etc/pve/nodes", stdout="pve1\n")
        self.lab.unreachable("pve2")
        result = self.lab.run("pve-snapshot", "101", "pre-x", "--dry-run")
        self.assertEqual(result.returncode, 2)
        self.assertIn("pass --node NODE", result.stderr)
        self.assertNotIn("check: ct 101 is on pve1: ok", result.stdout)
        with_node = self.lab.run("pve-snapshot", "101", "pre-x", "--node", "pve1", "--dry-run")
        self.assertEqual(with_node.returncode, 0, with_node.stderr)

    def test_a_vmid_on_two_nodes_needs_node(self):
        self.duplicate_101()
        result = self.lab.run("pve-snapshot", "101", "before-x", "--yes")
        self.assertEqual(result.returncode, 2)
        self.assertIn("VMID 101 is on pve1 and pve2; pass --node NODE", result.stderr)
        self.assertEqual(self.lab.commands("admin"), [])

    def test_node_option_targets_that_node_in_a_dry_run(self):
        self.duplicate_101()
        result = self.lab.run("pve-snapshot", "101", "before-x", "--node", "pve2", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("check: ct 101 is on pve2: ok\n", result.stdout)
        self.assertIn("step 1/1: ssh pve2-admin -- pct snapshot 101 before-x\n", result.stdout)
        self.assertEqual(self.lab.commands("admin"), [])
        self.assertNotIn("pve1", {call["node"] for call in self.lab.calls()})

    def test_without_yes_and_terminal_nothing_runs(self):
        result = self.lab.run("pve-snapshot", "101", "before-x")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.lab.commands("admin"), [])

    def test_yes_takes_and_verifies(self):
        self.lab.respond("pve1", "pct snapshot 101 before-x")
        listed = fx.SNAPSHOTS["101"].replace(" `-> current", " `-> before-x  2026-07-01 10:00:00  no-description\n"
                                                              "    `-> current")
        self.lab.respond_seq("pve1", "pct listsnapshot 101", {"stdout": fx.SNAPSHOTS["101"]}, {"stdout": listed})
        result = self.lab.run("pve-snapshot", "101", "before-x", "--yes")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.endswith("result: exit 0\nverify: snapshot before-x is listed: ok\n"))
        self.assertEqual(self.lab.commands("admin"), ["pct snapshot 101 before-x"])

    def test_verify_fails_when_the_snapshot_is_missing(self):
        self.lab.respond("pve1", "pct snapshot 101 before-x")
        result = self.lab.run("pve-snapshot", "101", "before-x", "--yes")
        self.assertEqual(result.returncode, 1)
        self.assertIn("verify: snapshot before-x is not listed after the command: FAILED", result.stdout)

    def test_pre_checks(self):
        existing = self.lab.run("pve-snapshot", "101", "pre-upgrade", "--dry-run")
        self.assertEqual(existing.returncode, 1)
        self.assertIn("ct 101 already has a snapshot named pre-upgrade: FAILED", existing.stdout)
        self.lab.respond("pve1", "pct config 101",
                         stdout=fx.CONFIGS["101"].replace("local-lvm:vm-101-disk-0", "local:101/vm-101-disk-0.raw"))
        raw = self.lab.run("pve-snapshot", "101", "x1", "--dry-run")
        self.assertEqual(raw.returncode, 1)
        self.assertIn("rootfs of ct 101 is on local (dir), which cannot snapshot it", raw.stdout)

    def test_passthrough_disk_fails_the_check(self):
        self.lab.respond("pve2", "qm config 200", stdout=fx.CONFIGS["200"] +
                         "scsi1: /dev/disk/by-id/ata-EXAMPLE_SERIAL,iothread=1,size=1863G\n")
        result = self.lab.run("pve-snapshot", "200", "x1", "--yes")
        self.assertEqual(result.returncode, 1)
        self.assertIn("scsi1 of vm 200 is a passthrough device", result.stdout)
        self.assertEqual(self.lab.commands("admin"), [])

    def test_unreadable_snapshot_list_fails_the_check(self):
        self.lab.respond("pve1", "pct listsnapshot 101", exit=255, stderr="ssh: boom\n")
        result = self.lab.run("pve-snapshot", "101", "before-x", "--dry-run")
        self.assertEqual(result.returncode, 1)
        self.assertIn("check: cannot read the snapshots of ct 101: FAILED", result.stdout)
        self.assertNotIn("is unused: ok", result.stdout)

    def test_empty_snapshot_list_fails_the_check(self):
        self.lab.respond("pve1", "pct listsnapshot 101", stdout="")
        result = self.lab.run("pve-snapshot", "101", "before-x", "--dry-run")
        self.assertEqual(result.returncode, 1)
        self.assertIn("check: cannot read the snapshots of ct 101: FAILED", result.stdout)

    def test_failed_step_exits_1_without_verify(self):
        self.lab.respond("pve1", "pct snapshot 101 before-x", exit=255, stderr="ssh: lost\n")
        result = self.lab.run("pve-snapshot", "101", "before-x", "--yes")
        self.assertEqual(result.returncode, 1)
        self.assertIn("result: exit 255", result.stdout)
        self.assertNotIn("verify:", result.stdout)
        self.assertEqual(self.lab.commands("admin"), ["pct snapshot 101 before-x"])

    def test_reserved_and_short_names_are_usage_errors(self):
        for name in ("a", "current", "pending", "vzdump"):
            result = self.lab.run("pve-snapshot", "101", name, "--yes")
            self.assertEqual(result.returncode, 2, name)
        self.assertEqual(self.lab.commands("admin"), [])

    def test_mistyped_flag_never_runs(self):
        for args in (("101", "x1", "--dryrun"), ("--dryrun", "101", "x1")):
            result = self.lab.run("pve-snapshot", *args, "--yes")
            self.assertEqual(result.returncode, 2)
        self.assertEqual(self.lab.commands("admin"), [])

    def test_usage_and_vm(self):
        self.assertEqual(self.lab.run("pve-snapshot", "101", "1bad").returncode, 2)
        self.assertEqual(self.lab.run("pve-snapshot", "101").returncode, 2)
        vm = self.lab.run("pve-snapshot", "200", "x1", "--dry-run")
        self.assertIn("step 1/1: ssh pve2-admin -- qm snapshot 200 x1\n", vm.stdout)


NEW_BACKUP = "nas-backup:backup/vzdump-lxc-101-2026_07_01-10_00_00.tar.zst  tar.zst backup     412399999 101\n"
VZDUMP = "vzdump 101 --mode snapshot --compress zstd --storage nas-backup --notes-template pre-change {{guestname}}"


class BackupTest(unittest.TestCase):
    def setUp(self):
        self.lab = Lab()
        self.addCleanup(self.lab.close)
        fx.load(self.lab)
        self.lab.write_env("PVE_BACKUP_STORAGE=nas-backup\n")

    def test_dry_run(self):
        result = self.lab.run("pve-backup", "101", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.startswith(
            "check: ct 101 is on pve1: ok\ncheck: storage nas-backup is active on pve1: ok\n"
            "check: storage nas-backup accepts backups: ok\ntarget: ct 101 on pve1\npath: trivial\n"))
        self.assertIn("step 1/1: ssh pve1-admin -- vzdump 101 --mode snapshot --compress zstd "
                      "--storage nas-backup --notes-template ", result.stdout)
        self.assertEqual(self.lab.commands("admin"), [])

    def test_yes_backs_up_and_finds_the_new_archive(self):
        self.lab.respond("pve1", VZDUMP, stdout="INFO: Backup job finished successfully\n")
        self.lab.respond_seq("pve1", "pvesm list nas-backup --content backup",
                             {"stdout": fx.BACKUPS}, {"stdout": fx.BACKUPS + NEW_BACKUP})
        result = self.lab.run("pve-backup", "101", "--yes")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("verify: new backup nas-backup:backup/vzdump-lxc-101-2026_07_01-10_00_00.tar.zst: ok\n",
                      result.stdout)
        self.assertEqual(self.lab.calls()[-2]["argv"][-1], "pre-change {{guestname}}")

    def test_no_new_archive_fails(self):
        self.lab.respond("pve1", VZDUMP)
        result = self.lab.run("pve-backup", "101", "--yes")
        self.assertEqual(result.returncode, 1)
        self.assertIn("no new backup of ct 101 on nas-backup: FAILED", result.stdout)

    def test_failed_step_exits_1_without_verify(self):
        self.lab.respond("pve1", VZDUMP, exit=255, stderr="ssh: lost\n")
        result = self.lab.run("pve-backup", "101", "--yes")
        self.assertEqual(result.returncode, 1)
        self.assertIn("result: exit 255", result.stdout)
        self.assertNotIn("verify:", result.stdout)
        self.assertEqual(len(self.lab.commands("admin")), 1)

    def test_without_yes_and_terminal_nothing_runs(self):
        result = self.lab.run("pve-backup", "101")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.lab.commands("admin"), [])

    def test_mistyped_flag_never_runs(self):
        result = self.lab.run("pve-backup", "101", "--dryrun", "--yes")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.lab.commands("admin"), [])

    def test_storage_checks(self):
        self.lab.write_env("")
        self.assertEqual(self.lab.run("pve-backup", "101", "--dry-run").returncode, 2)
        wrong = self.lab.run("pve-backup", "101", "--storage", "local-lvm", "--dry-run")
        self.assertEqual(wrong.returncode, 1)
        self.assertIn("storage local-lvm does not accept backups (content: rootdir,images)", wrong.stdout)
        self.lab.respond("pve1", "pvesm status",
                         stdout=fx.pvesm_status().replace("nas-backup         nfs     active",
                                                          "nas-backup         nfs   inactive"))
        inactive = self.lab.run("pve-backup", "101", "--storage", "nas-backup", "--dry-run")
        self.assertEqual(inactive.returncode, 1)
        self.assertIn("storage nas-backup is inactive on pve1", inactive.stdout)

    def test_full_source_pool_is_a_warning(self):
        self.lab.respond("pve1", "pvesm status", stdout=fx.pvesm_status().replace("27.35%", "93.00%"))
        result = self.lab.run("pve-backup", "101", "--dry-run")
        self.assertEqual(result.returncode, 0)
        self.assertIn("check: local-lvm, which holds rootfs, is at 93.00%: the snapshot-mode backup may fail: WARNING",
                      result.stdout)


if __name__ == "__main__":
    unittest.main()
