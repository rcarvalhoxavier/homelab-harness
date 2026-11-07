import unittest

from tests import pvefixtures as fx
from tests.toolkit import Lab

TWO_NODE = ("two_node is set: quorum survives one node at the cost of a split-brain risk; "
            "a QDevice on an independent machine is the durable fix")


def recommendations(out: str) -> str:
    return out.split("== recommendations\n", 1)[1]


class CapacityTest(unittest.TestCase):
    def setUp(self):
        self.lab = Lab()
        self.addCleanup(self.lab.close)
        fx.load(self.lab)

    def append(self, node: str, command: str, text: str):
        self.lab.responses[node][command]["stdout"] += text

    def test_a_healthy_lab(self):
        result = self.lab.run("pve-capacity")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        out = result.stdout
        for line in ("pve-capacity 1\n== node pve1\nvg pve: 16.00 GiB free\n",
                     "thin pool pve/data: 348.82 GiB, data 27.35%, metadata 1.87%\n",
                     "disks by storage:\n  local (dir): 13.32% used\n  local-lvm (lvmthin): 27.35% used\n"
                     "        8.00 GiB  local-lvm:vm-101-disk-0  pihole\n",
                     "orphans:\n  (none)\n", "storage.cfg:\n  local (dir), here: active\n",
                     "  (no configuration problem found)\n", "quorum: 2 of 2 votes, quorate Yes\n"):
            self.assertIn(line, out)
        self.assertIn("       32.00 GiB  local-lvm:vm-200-disk-0  nas\n        8.00 GiB  local-lvm:vm-102-disk-0  pihole\n", out)
        self.assertEqual(recommendations(out), f"1. [cluster] {TWO_NODE}\n")
        self.assertEqual(self.lab.commands("admin"), [])

    def test_a_full_thin_pool(self):
        self.lab.respond("pve1", fx.LVS_POOLS, stdout="  pve data 374538764288 96.50 3.10\n")
        result = self.lab.run("pve-capacity")
        self.assertEqual(result.returncode, 1)
        recs = recommendations(result.stdout)
        self.assertTrue(recs.startswith("1. [pve1] thin pool pve/data at 96.50% (limit 85%): extend it into "
                                        "the 16.00 GiB free in VG pve (reversible, moves no data)"))
        self.assertIn("above 95% snapshots and moves may fail", recs)

    def test_an_inactive_thin_pool_is_reported_not_a_crash(self):
        self.lab.respond("pve1", fx.LVS_POOLS, stdout="  pve data 374538764288\n")
        result = self.lab.run("pve-capacity")
        self.assertEqual(result.returncode, 1)
        self.assertIn("thin pool pve/data: 348.82 GiB, inactive (usage not reported)\n", result.stdout)
        self.assertIn("[pve1] thin pool pve/data is inactive", recommendations(result.stdout))

    def test_a_failed_zpool_list_with_a_zfs_storage_is_a_crit(self):
        self.append("pve1", "pvesm status",
                    "tank           zfspool     active       965738496       101234567       864503929   10.48%\n")
        self.lab.respond("pve1", "pvesm list tank", stdout="Volid Format  Type Size VMID\n")
        self.lab.respond("pve1", fx.ZPOOL, stderr="internal error: failed to initialize ZFS library\n", exit=1)
        result = self.lab.run("pve-capacity", "--node", "pve1")
        self.assertEqual(result.returncode, 1)
        self.assertIn("  (could not read zpool on pve1)\n", result.stdout)

    def test_orphans(self):
        self.append("pve1", fx.LVS_ALL, "  vm-999-disk-0 pve 4294967296 10.00\n"
                                        "  snap_vm-101-disk-0_old pve 8589934592 41.20\n")
        self.append("pve1", "pvesm list local-lvm", "local-lvm:vm-999-disk-0  raw     images     4294967296 999\n")
        self.append("pve1", "pvesm list local", "local:300/vm-300-disk-1.qcow2 qcow2 images 2147483648 300\n")
        result = self.lab.run("pve-capacity")
        self.assertEqual(result.returncode, 0, result.stderr)
        for line in ("  lv pve/vm-999-disk-0 4.00 GiB: disk of a guest that is on no node\n",
                     "  lv pve/snap_vm-101-disk-0_old 8.00 GiB: snapshot that Proxmox does not list\n",
                     "  volume local:300/vm-300-disk-1.qcow2 2.00 GiB: no guest config references it\n"):
            self.assertIn(line, result.stdout)
        self.assertNotIn("volume local-lvm:vm-999-disk-0", result.stdout)
        self.assertIn("[pve1] lv pve/vm-999-disk-0", recommendations(result.stdout))
        self.assertIn("[pve1] volume local:300/vm-300-disk-1.qcow2", recommendations(result.stdout))

    def test_a_volume_of_an_existing_guest_is_never_an_orphan(self):
        # real qm config prints the current config only: a snapshot's vmstate volume and a disk
        # that only a snapshot references appear in no config line, but belong to VM 200
        self.append("pve2", "qm config 200", "parent: before\n")
        self.lab.respond("pve2", "qm listsnapshot 200",
                         stdout="`-> before                      2026-06-30 08:00:00     with RAM\n"
                                "    `-> current                                         You are here!\n")
        self.append("pve2", "pvesm list local-lvm",
                    "local-lvm:vm-200-disk-1       raw images 8589934592 200\n"
                    "local-lvm:vm-200-state-before raw images 4819255296 200\n")
        self.append("pve2", fx.LVS_ALL, "  vm-200-disk-1 pve 8589934592 3.10\n"
                                        "  vm-200-state-before pve 4819255296 12.00\n")
        self.append("pve1", "pvesm list local", "local:101/vm-101-disk-1.qcow2 qcow2 images 2147483648 101\n")
        result = self.lab.run("pve-capacity")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        out = result.stdout
        for line in ("  lv pve/vm-200-disk-1 8.00 GiB: not in the current config of vm 200 (may belong to a snapshot)\n",
                     "  volume local-lvm:vm-200-state-before 4.49 GiB: not in the current config of vm 200 "
                     "(may belong to a snapshot)\n",
                     "  volume local:101/vm-101-disk-1.qcow2 2.00 GiB: not in the current config of ct 101 "
                     "(may belong to a snapshot)\n"):
            self.assertIn(line, out)
        self.assertNotIn("no guest config references it", out)
        self.assertNotIn("guest that is on no node", out)
        recs = recommendations(out)
        for volume in ("vm-200-disk-1", "vm-200-state-before", "vm-101-disk-1"):
            self.assertNotIn(volume, recs)

    def test_a_disk_of_a_guest_on_another_node_is_not_an_orphan(self):
        # shared LVM: pve1 sees the logical volume of VM 200, which runs on pve2
        self.append("pve1", fx.LVS_ALL, "  vm-200-disk-0 pve 34359738368 22.10\n"
                                        "  snap_vm-200-disk-0_gone pve 34359738368 22.10\n")
        result = self.lab.run("pve-capacity")
        out = result.stdout
        self.assertNotIn("lv pve/vm-200-disk-0", out)
        self.assertIn("  lv pve/snap_vm-200-disk-0_gone 32.00 GiB: snapshot that Proxmox does not list\n", out)
        self.assertNotIn("guest that is on no node", out)

    def test_an_unreadable_snapshot_list_is_not_an_orphan(self):
        self.append("pve1", fx.LVS_ALL, "  snap_vm-101-disk-0_pre-upgrade pve 8589934592 41.20\n")
        self.lab.respond("pve1", "pct listsnapshot 101", stderr="boom\n", exit=1)
        result = self.lab.run("pve-capacity")
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("snapshot that Proxmox does not list", result.stdout)
        self.assertIn("could not read snapshots of ct 101 on pve1", result.stdout)

    def test_cloud_init_and_vmstate_volumes_are_not_orphans(self):
        self.append("pve2", "qm config 200",
                    "ide0: local-lvm:vm-200-cloudinit,media=cdrom\nvmstate: local-lvm:vm-200-state-suspend\n")
        self.append("pve2", "pvesm list local-lvm",
                    "local-lvm:vm-200-cloudinit  raw images 4194304 200\n"
                    "local-lvm:vm-200-state-suspend raw images 1073741824 200\n"
                    "local-lvm:vm-300-disk-0 raw images 1073741824 300\n")
        out = self.lab.run("pve-capacity").stdout
        self.assertNotIn("volume local-lvm:vm-200-cloudinit", out)
        self.assertNotIn("volume local-lvm:vm-200-state", out)
        self.assertIn("volume local-lvm:vm-300-disk-0 1.00 GiB: no guest config references it", out)

    def test_an_empty_listsnapshot_is_a_broken_read_not_an_orphan(self):
        self.append("pve1", fx.LVS_ALL, "  snap_vm-101-disk-0_pre-upgrade pve 8589934592 41.20\n")
        self.lab.respond("pve1", "pct listsnapshot 101", stdout="")
        result = self.lab.run("pve-capacity", "--node", "pve1")
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("snapshot that Proxmox does not list", result.stdout)
        self.assertIn("could not read snapshots of ct 101 on pve1", result.stdout)

    def test_the_same_recommendation_on_two_nodes_names_both(self):
        for node in ("pve1", "pve2"):
            self.lab.respond(node, fx.LVS_POOLS, stdout="  pve data 374538764288\n")
        recs = recommendations(self.lab.run("pve-capacity").stdout)
        self.assertIn("[pve1] thin pool pve/data is inactive", recs)
        self.assertIn("[pve2] thin pool pve/data is inactive", recs)

    def test_a_cluster_member_missing_from_the_inventory_skips_the_orphan_check(self):
        # inventory/nodes lists pve1 only; pve2 is a member and runs VM 200, whose disk lives on a
        # shared storage that pve1 lists too: never an orphan, never a recommendation
        lab = Lab(nodes=("pve1",))
        self.addCleanup(lab.close)
        fx.load(lab)
        lab.responses["pve1"]["pvesm status"]["stdout"] += (
            "shared             nfs     active      1951350784       512340224      1439010560   26.26%\n")
        lab.respond("pve1", "pvesm list shared",
                    stdout="Volid                              Format  Type        Size VMID\n"
                           "shared:200/vm-200-disk-1.qcow2     qcow2   images 34359738368 200\n")
        result = lab.run("pve-capacity")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("orphans:\n  (orphan check skipped: cluster member pve2 is not in inventory/nodes)\n",
                      result.stdout)
        self.assertNotIn("vm-200-disk-1.qcow2 32.00 GiB: no guest config", result.stdout)
        self.assertNotIn("(none)", result.stdout.split("orphans:\n", 1)[1].split("storage.cfg:", 1)[0])
        self.assertNotIn("vm-200", recommendations(result.stdout))

    def test_unreadable_cluster_members_skip_the_orphan_check(self):
        for node in ("pve1", "pve2"):
            self.lab.respond(node, "pvecm nodes", stderr="homelab-collect: refused: pvecm nodes\n", exit=126)
        self.append("pve1", "pvesm list local", "local:300/vm-300-disk-1.qcow2 qcow2 images 2147483648 300\n")
        result = self.lab.run("pve-capacity", "--node", "pve1")
        self.assertIn("orphans:\n  (orphan check skipped: the cluster members of pve1, pve2 could not be read)\n",
                      result.stdout)
        self.assertNotIn("vm-300-disk-1.qcow2 2.00 GiB: no guest config", result.stdout)

    def test_members_of_one_cluster_are_read_once(self):
        result = self.lab.run("pve-capacity")
        self.assertEqual(result.returncode, 0, result.stderr)
        # one pvecm nodes for the orphan check (pve2 is a member of the list pve1 gave), and none
        # for the storage.cfg check beyond one per reported node
        self.assertEqual(self.lab.commands("collect").count("pvecm nodes"), 3)

    def test_an_unreadable_guest_config_is_a_line_on_stdout(self):
        self.lab.respond("pve2", "qm config 200", stderr="boom\n", exit=2)
        result = self.lab.run("pve-capacity", "--node", "pve1")
        self.assertEqual(result.returncode, 1)
        orphans = result.stdout.split("orphans:\n", 1)[1].split("storage.cfg:", 1)[0]
        self.assertEqual(orphans, "  (could not read the config of vm 200 on pve2)\n"
                                  "  (unreferenced-volume check skipped: not every guest config could be read)\n")

    def test_an_unreachable_node_skips_the_unreferenced_check(self):
        self.lab.unreachable("pve2")
        result = self.lab.run("pve-capacity")
        self.assertEqual(result.returncode, 1)
        self.assertIn("(unreferenced-volume check skipped: not every guest config could be read)", result.stdout)
        self.assertIn("== node pve2\nUNREACHABLE\n", result.stdout)
        self.assertEqual(result.stderr.count("No route to host; see docs/ssh-access.md"), 1, result.stderr)

    def test_failed_reads_are_never_a_plausible_section(self):
        for command, what in ((fx.VGS, "volume groups"), (fx.LVS_POOLS, "thin pools"),
                              ("pvesm status", "storage"), ("cat /etc/pve/storage.cfg", "storage.cfg"),
                              ("pct list", "guests"), (fx.LVS_ALL, "logical volumes")):
            with self.subTest(command=command):
                self.lab.respond("pve1", command, stderr="boom\n", exit=1)
                result = self.lab.run("pve-capacity", "--node", "pve1")
                self.assertEqual(result.returncode, 1)
                self.assertIn(f"could not read {what} on pve1", result.stdout)
                fx.load(self.lab)

    def test_a_refused_pvecm_status_is_a_crit_not_standalone(self):
        self.lab.respond("pve1", "pvecm status", stderr="homelab-collect: refused: pvecm status\n", exit=126)
        result = self.lab.run("pve-capacity", "--node", "pve1")
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("quorum: standalone", result.stdout)
        self.assertIn("could not read quorum on pve1", result.stdout)

    def test_an_unreadable_corosync_conf_is_not_a_verdict(self):
        self.lab.respond("pve1", "cat /etc/pve/corosync.conf", stderr="ssh: connection lost\n", exit=255)
        result = self.lab.run("pve-capacity", "--node", "pve1")
        self.assertEqual(result.returncode, 1)
        self.assertIn("could not read quorum on pve1", result.stdout)
        self.assertNotIn("quorum: standalone", result.stdout)
        self.assertNotIn("two votes without two_node", result.stdout)

    def test_a_cluster_that_is_not_quorate_is_critical(self):
        self.lab.respond("pve1", "pvecm status", **fx.PVECM_NOT_QUORATE)
        result = self.lab.run("pve-capacity", "--node", "pve1")
        self.assertEqual(result.returncode, 1)
        self.assertIn("quorum: 1 of 2 votes, quorate No\n", result.stdout)
        self.assertIn("the cluster is not quorate: 1 of 2 votes", recommendations(result.stdout))
        self.assertNotIn("standalone", result.stdout)

    def test_corosync_down_is_a_crit_not_standalone(self):
        self.lab.respond("pve1", "pvecm status", **fx.PVECM_COROSYNC_DOWN)
        result = self.lab.run("pve-capacity", "--node", "pve1")
        self.assertEqual(result.returncode, 1)
        self.assertIn("could not read quorum on pve1", result.stdout)
        self.assertNotIn("standalone", result.stdout)

    def test_storage_cfg_problems_are_recommended_once(self):
        extra = "\ndir: scratch\n\tpath /srv\n\tshared 1\n\tnodes pve1,pve3\n\tcontent images\n"
        for node in ("pve1", "pve2"):
            self.append(node, "cat /etc/pve/storage.cfg", extra)
        out = self.lab.run("pve-capacity").stdout
        self.assertEqual(out.count("    ghost node: pve3 is not a cluster member\n"), 2)
        recs = recommendations(out)
        self.assertEqual(recs.count("storage scratch lists node pve3"), 1)
        self.assertEqual(recs.count("storage scratch has shared 1 on a dir storage: correct only if the path is a "
                                    "network mount shared by all nodes; otherwise set shared 0"), 1)
        self.assertNotIn("is a local dir marked shared 1", out)

    def test_a_standalone_node_uses_its_real_proxmox_name(self):
        # inventory says pve1; Proxmox calls the node pve-a; a storage limited to pve-a is fine
        fx.standalone(self.lab, "pve1")
        self.lab.respond("pve1", "ls /etc/pve/nodes", stdout="pve-a\n")
        self.append("pve1", "cat /etc/pve/storage.cfg", "\nlvm: fast\n\tvgname fast\n\tnodes pve-a\n\tcontent images\n")
        result = self.lab.run("pve-capacity", "--node", "pve1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("ghost node", result.stdout)
        self.assertNotIn("not a cluster member", recommendations(result.stdout))
        self.assertIn("quorum: standalone\n", result.stdout)

    def test_unreadable_node_names_on_a_standalone_node_give_no_node_advice(self):
        # a failed listing makes the quorum unreadable (pmxcfs may be down); a listing without a
        # node name leaves the quorum standalone but the members unknown
        for answer, unread in (({"exit": 255, "stderr": "ssh: connection lost\n"}, "quorum"),
                               ({"stdout": "?? bad name\n"}, "cluster members")):
            with self.subTest(unread=unread):
                lab = Lab()
                self.addCleanup(lab.close)
                fx.load(lab)
                fx.standalone(lab, "pve1")
                lab.respond("pve1", "ls /etc/pve/nodes", **answer)
                cfg = lab.responses["pve1"]["cat /etc/pve/storage.cfg"]["stdout"]
                lab.respond("pve1", "cat /etc/pve/storage.cfg",
                            stdout=cfg + "\nlvm: fast\n\tvgname fast\n\tnodes pve-a\n\tcontent images\n")
                result = lab.run("pve-capacity", "--node", "pve1")
                self.assertEqual(result.returncode, 1)
                self.assertIn(f"(could not read {unread} on pve1)", result.stdout)
                self.assertIn("(ghost-node check skipped: cluster members unknown)", result.stdout)
                self.assertNotIn("not a cluster member", result.stdout)

    def test_a_ghost_vote(self):
        for node in ("pve1", "pve2"):
            text = self.lab.responses[node]["pvecm status"]["stdout"]
            self.lab.respond(node, "pvecm status", stdout=text.replace("Expected votes:   2", "Expected votes:   3"))
            self.lab.respond(node, "ls /etc/pve/nodes", stdout="pve1\npve2\npve3\n")
        out = self.lab.run("pve-capacity").stdout
        self.assertIn("  ghost vote: 3 votes expected, 2 present; registered but not members: pve3\n", out)
        self.assertIn("the cluster expects 3 votes and 2 are present; registered but not members: pve3 "
                      "(remove with pvecm delnode)", recommendations(out))

    def test_standalone_nodes(self):
        for node in ("pve1", "pve2"):
            fx.standalone(self.lab, node)
        out = self.lab.run("pve-capacity").stdout
        self.assertIn("quorum: standalone\n", out)
        self.assertEqual(recommendations(out), "(no action recommended)\n")

    def test_unknown_options_are_a_usage_error(self):
        for args in (("--dryrun",), ("--node",), ("stray",)):
            with self.subTest(args=args):
                self.assertEqual(self.lab.run("pve-capacity", *args).returncode, 2)

    def test_deterministic_and_one_node(self):
        self.assertEqual(self.lab.run("pve-capacity").stdout, self.lab.run("pve-capacity").stdout)
        self.assertNotIn("== node pve2", self.lab.run("pve-capacity", "--node", "pve1").stdout)


if __name__ == "__main__":
    unittest.main()
