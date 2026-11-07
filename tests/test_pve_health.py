import unittest

from tests import pvefixtures as fx
from tests.toolkit import Lab


class HealthTest(unittest.TestCase):
    def setUp(self):
        self.lab = Lab()
        self.addCleanup(self.lab.close)
        fx.load(self.lab)
        self.lab.write_env("PVE_BACKUP_STORAGE=nas-backup\n")

    def health(self, *args):
        return self.lab.run("pve-health", "--today", "2026-07-01", *args)

    def test_a_healthy_lab(self):
        result = self.health()
        self.assertEqual(result.returncode, 0, result.stderr)
        out = result.stdout
        self.assertTrue(out.startswith("pve-health 1 | 2026-07-01\n== node pve1\n"
                                       "version: pve-manager/8.4.1/2a5fa54a8503f96d (running kernel: 6.8.12-10-pve)\n"))
        for line in ("storage local-lvm lvmthin active 27.35%\n", "quorum: 2/2 votes, quorate Yes\n",
                     "guest ct 101 pihole running\n", "backup ct 101 2026-06-30T23:00:02\n",
                     "guest vm 200 nas running\n", "backup vm 200 2026-06-30T23:20:11\n",
                     "memory: 31.16 GiB total, 10.00 GiB used; swap 8.00 GiB total, 0.00 GiB used\n",
                     "rootfs: 14% used, 76.91 GiB available\n"):
            self.assertIn(line, out)
        self.assertTrue(out.endswith("summary: 0 CRIT, 0 WARN, 0 unreachable\n"))
        self.assertEqual(self.lab.commands("admin"), [])

    def test_stale_backups(self):
        result = self.lab.run("pve-health", "--today", "2026-07-05")
        self.assertEqual(result.returncode, 0)
        self.assertIn("finding WARN ct 101 (pihole) latest backup is 5 days old\n", result.stdout)
        self.assertIn("summary: 0 CRIT, 3 WARN, 0 unreachable\n", result.stdout)

    def test_storage_above_the_limit_is_critical(self):
        status = fx.pvesm_status().replace("27.35%", "91.20%")
        self.lab.respond("pve1", "pvesm status", stdout=status)
        result = self.health()
        self.assertEqual(result.returncode, 1)
        self.assertIn("finding CRIT storage local-lvm at 91.20% (limit 85%)\n", result.stdout)

    def test_stopped_guest_and_missing_backup(self):
        self.lab.respond("pve1", "pct list", stdout=fx.pct_list([("101", "stopped", "pihole")]))
        backups = "".join(line + "\n" for line in fx.BACKUPS.splitlines() if "lxc-101" not in line)
        for node in ("pve1", "pve2"):
            self.lab.respond(node, "pvesm list nas-backup --content backup", stdout=backups)
        result = self.health()
        self.assertIn("finding WARN ct 101 (pihole) is stopped\n", result.stdout)
        self.assertIn("backup ct 101 none\n", result.stdout)
        self.assertIn("finding WARN ct 101 (pihole) has no backup on nas-backup\n", result.stdout)

    def test_backup_storage_unavailable_on_one_node_warns_once(self):
        # pvesm status lists only the storages enabled for the node (nodes in storage.cfg)
        status = self.lab.responses["pve2"]["pvesm status"]["stdout"]
        self.lab.respond("pve2", "pvesm status",
                         stdout="".join(line for line in status.splitlines(True) if "nas-backup" not in line))
        self.lab.respond("pve2", "pvesm list nas-backup --content backup", exit=2,
                         stderr="storage 'nas-backup' is not available on node 'pve2'\n")
        result = self.health()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(result.stdout.count("finding WARN"), 1)
        self.assertIn("backups: nas-backup unavailable on this node\n", result.stdout)
        self.assertIn("finding WARN backup storage nas-backup unavailable on pve2\n", result.stdout)
        self.assertNotIn("has no backup", result.stdout)

    def test_a_listed_backup_storage_that_cannot_be_listed_is_a_crit(self):
        self.lab.respond("pve2", "pvesm list nas-backup --content backup", exit=2,
                         stderr="storage 'nas-backup' is not online\n")
        result = self.health()
        self.assertEqual(result.returncode, 1)
        self.assertIn("finding CRIT could not read backups on pve2\n", result.stdout)
        self.assertNotIn("unavailable", result.stdout)
        self.assertIn("is not online", result.stderr)

    def test_an_inactive_backup_storage_warns_with_its_state_not_a_failed_read(self):
        status = self.lab.responses["pve2"]["pvesm status"]["stdout"]
        self.lab.respond("pve2", "pvesm status", stdout=status.replace("nfs     active", "nfs   inactive"))
        self.lab.respond("pve2", "pvesm list nas-backup --content backup", exit=2,
                         stderr="storage 'nas-backup' is not online\n")
        result = self.health()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("backups: nas-backup inactive on this node\n", result.stdout)
        self.assertIn("finding WARN backup storage nas-backup is inactive on pve2\n", result.stdout)
        self.assertNotIn("could not read backups", result.stdout)
        self.assertNotIn("has no backup", result.stdout)
        # the backup section already warns: the storage line adds no second finding
        self.assertNotIn("finding WARN storage nas-backup", result.stdout)
        self.assertIn("summary: 0 CRIT, 1 WARN", result.stdout)

    def test_an_inactive_storage_warns(self):
        status = self.lab.responses["pve1"]["pvesm status"]["stdout"]
        self.lab.respond("pve1", "pvesm status", stdout=status.replace(
            "lvmthin     active       365760512       100022210       265738302   27.35%",
            "lvmthin   inactive               0               0               0    0.00%"))
        result = self.health("--node", "pve1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("storage local-lvm lvmthin inactive -\n", result.stdout)
        self.assertIn("finding WARN storage local-lvm is inactive on pve1\n", result.stdout)

    def test_a_disabled_storage_is_no_finding(self):
        status = self.lab.responses["pve1"]["pvesm status"]["stdout"]
        self.lab.respond("pve1", "pvesm status", stdout=status.replace(
            "lvmthin     active       365760512       100022210       265738302   27.35%",
            "lvmthin   disabled               0               0               0      N/A"))
        result = self.health("--node", "pve1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("storage local-lvm lvmthin disabled -\n", result.stdout)
        self.assertNotIn("finding WARN storage local-lvm", result.stdout)

    def test_backups_on_a_proxmox_backup_server(self):
        self.lab.write_env("PVE_BACKUP_STORAGE=pbs\n")
        for node in ("pve1", "pve2"):
            self.lab.respond(node, "pvesm list pbs --content backup", stdout=fx.PBS_BACKUPS)
        result = self.health()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for line in ("backup ct 101 2026-06-30T23:00:02\n", "backup ct 102 2026-06-30T23:10:04\n",
                     "backup vm 200 2026-06-30T23:20:11\n"):
            self.assertIn(line, result.stdout)
        self.assertNotIn("has no backup", result.stdout)

    def test_a_backup_of_another_guest_type_does_not_count(self):
        # the same VMID as a VM elsewhere (two clusters on one backup storage): vzdump-qemu-101 is
        # not a backup of CT 101
        backups = "".join(line.replace("vzdump-lxc-101", "vzdump-qemu-101").replace("tar.zst", "vma.zst") + "\n"
                          for line in fx.BACKUPS.splitlines())
        for node in ("pve1", "pve2"):
            self.lab.respond(node, "pvesm list nas-backup --content backup", stdout=backups)
        result = self.health("--node", "pve1")
        self.assertIn("backup ct 101 none\n", result.stdout)
        self.assertIn("finding WARN ct 101 (pihole) has no backup on nas-backup\n", result.stdout)

    def test_degraded_zfs_pool(self):
        self.lab.respond("pve1", fx.ZPOOL, stdout="rpool\t999653638144\t123456789012\t876196849132\t12\tDEGRADED\n")
        result = self.health()
        self.assertEqual(result.returncode, 1)
        self.assertIn("zpool rpool 12% DEGRADED\n", result.stdout)
        self.assertIn("finding CRIT zpool rpool is DEGRADED\n", result.stdout)

    def test_a_failed_zpool_list_with_a_zfs_storage_is_a_crit(self):
        # zfsutils is part of Proxmox VE and `zpool list` exits 0 without pools: with a zfspool
        # storage, a failure is a broken read, never "no ZFS"
        self.lab.responses["pve1"]["pvesm status"]["stdout"] += (
            "tank           zfspool     active       965738496       101234567       864503929   10.48%\n")
        self.lab.respond("pve1", fx.ZPOOL, stderr="internal error: failed to initialize ZFS library\n", exit=1)
        result = self.health("--node", "pve1")
        self.assertEqual(result.returncode, 1)
        self.assertIn("finding CRIT could not read zpool on pve1\n", result.stdout)
        self.assertIn("failed to initialize ZFS library", result.stderr)

    def test_a_failed_zpool_list_without_a_zfs_storage_is_not_applicable(self):
        self.lab.respond("pve1", fx.ZPOOL, stderr="The ZFS modules are not loaded.\n", exit=1)
        result = self.health("--node", "pve1")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("zpool", result.stdout)

    def test_standalone_and_unreachable(self):
        fx.standalone(self.lab, "pve1")
        self.lab.unreachable("pve2")
        result = self.health()
        self.assertEqual(result.returncode, 1)
        self.assertIn("quorum: standalone\n", result.stdout)
        self.assertIn("== node pve2\nUNREACHABLE\n", result.stdout)
        self.assertIn("summary: 0 CRIT, 0 WARN, 1 unreachable\n", result.stdout)
        # the reason ssh gave, and where to look; stdout stays the report
        self.assertIn("pve2: the collect alias does not connect (exit 255): "
                      "ssh: connect to host pve2 port 22: No route to host; see docs/ssh-access.md", result.stderr)
        self.assertNotIn("No route", result.stdout)

    def test_a_cluster_that_is_not_quorate_is_critical(self):
        # corosync-quorumtool exits 2 when not quorate: that is a cluster, never "standalone"
        self.lab.respond("pve1", "pvecm status", **fx.PVECM_NOT_QUORATE)
        result = self.health("--node", "pve1")
        self.assertEqual(result.returncode, 1)
        self.assertIn("quorum: 1/2 votes, quorate No\n", result.stdout)
        self.assertIn("finding CRIT cluster not quorate (1 of 2 votes)\n", result.stdout)
        self.assertNotIn("standalone", result.stdout)

    def test_corosync_down_or_unparseable_quorum_is_critical(self):
        for answer in (fx.PVECM_COROSYNC_DOWN, fx.ok("garbage\n"),
                       {"stdout": "", "exit": 255, "stderr": "ssh: connection lost\n"}):
            with self.subTest(answer=answer):
                self.lab.respond("pve1", "pvecm status", **answer)
                result = self.health("--node", "pve1")
                self.assertEqual(result.returncode, 1)
                self.assertIn("finding CRIT could not read quorum on pve1\n", result.stdout)
                self.assertNotIn("standalone", result.stdout)

    def test_a_cluster_file_system_that_is_down_is_critical(self):
        fx.pmxcfs_down(self.lab, "pve1")
        result = self.health("--node", "pve1")
        self.assertEqual(result.returncode, 1)
        self.assertIn("finding CRIT could not read quorum on pve1\n", result.stdout)
        self.assertNotIn("standalone", result.stdout)
        self.assertIn("cannot access '/etc/pve/nodes'", result.stderr)

    def test_an_unreadable_corosync_conf_is_critical(self):
        self.lab.respond("pve1", "cat /etc/pve/corosync.conf", exit=126,
                         stderr="homelab-collect: refused: cat /etc/pve/corosync.conf\n")
        result = self.health("--node", "pve1")
        self.assertEqual(result.returncode, 1)
        self.assertIn("finding CRIT could not read quorum on pve1\n", result.stdout)
        self.assertNotIn("standalone", result.stdout)

    def test_one_node_and_no_backup_storage(self):
        self.lab.write_env("")
        result = self.health("--node", "pve1")
        self.assertNotIn("== node pve2", result.stdout)
        self.assertNotIn("\nbackup ", result.stdout)

    def test_deterministic_and_usage(self):
        self.assertEqual(self.health().stdout, self.health().stdout)
        self.assertEqual(self.lab.run("pve-health", "--today", "yesterday").returncode, 2)
        self.assertEqual(self.lab.run("pve-health", "--node").returncode, 2)
        self.assertEqual(self.lab.run("pve-health", "--node", "pve9").returncode, 2)

    def test_failed_reads_after_the_node_answered_are_not_ok(self):
        # ssh failure (255) on the memory read, dispatcher refusal (126) on the quorum read,
        # and a failed guest listing must each surface as a CRIT finding, never as an OK line
        self.lab.respond("pve1", "free -b", exit=255, stderr="ssh: connection lost\n")
        self.lab.respond("pve1", "pvecm status", exit=126, stderr="homelab-collect: refused: pvecm status\n")
        self.lab.respond("pve2", "pct list", exit=255, stderr="ssh: connection lost\n")
        result = self.health()
        self.assertEqual(result.returncode, 1)
        out = result.stdout
        self.assertIn("finding CRIT could not read memory on pve1\n", out)
        self.assertIn("finding CRIT could not read quorum on pve1\n", out)
        self.assertIn("finding CRIT could not read guests on pve2\n", out)
        self.assertNotIn("quorum: standalone", out.split("== node pve2")[0])
        self.assertNotIn("memory: 0.00", out)
        self.assertIn("summary: 3 CRIT, 0 WARN, 0 unreachable\n", out)

    def test_empty_or_unparseable_reads_are_critical(self):
        self.lab.respond("pve1", "pveversion", stdout="")
        self.lab.respond("pve1", "free -b", stdout="garbage\n")
        self.lab.respond("pve2", "pvesm status", stdout="")
        result = self.health()
        self.assertEqual(result.returncode, 1)
        out = result.stdout
        self.assertIn("finding CRIT could not read version on pve1\n", out)
        self.assertIn("finding CRIT could not read memory on pve1\n", out)
        self.assertIn("finding CRIT could not read storage on pve2\n", out)
        self.assertNotIn("version: \n", out)
        self.assertNotIn("memory: 0.00", out)
        self.assertIn("summary: 3 CRIT, 0 WARN, 0 unreachable\n", out)


if __name__ == "__main__":
    unittest.main()
