import unittest

from tests import pvefixtures as fx
from tests.toolkit import Lab


def indent(text: str, prefix: str = "  ") -> str:
    return "".join(prefix + line + "\n" for line in text.splitlines())


class GuestStateTest(unittest.TestCase):
    def setUp(self):
        self.lab = Lab()
        self.addCleanup(self.lab.close)
        fx.load(self.lab)
        self.lab.write_env("PVE_BACKUP_STORAGE=nas-backup\n")

    def test_container(self):
        result = self.lab.run("pve-state", "101")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout,
                         "pve-state 1 | ct 101 on pve1\nstatus: running\nconfig:\n" + indent(fx.CONFIGS["101"]) +
                         "snapshots:\n  pre-upgrade 2026-06-01T10:00:00\n"
                         "volumes:\n  rootfs local-lvm vm-101-disk-0 8G\n"
                         "backups on nas-backup:\n"
                         "  2026-06-29T23:00:03 nas-backup:backup/vzdump-lxc-101-2026_06_29-23_00_03.tar.zst\n"
                         "  2026-06-30T23:00:02 nas-backup:backup/vzdump-lxc-101-2026_06_30-23_00_02.tar.zst\n")
        self.assertEqual(self.lab.commands("admin"), [])

    def test_vm_without_backup_storage(self):
        self.lab.write_env("")
        result = self.lab.run("pve-state", "200")
        self.assertEqual(result.stdout,
                         "pve-state 1 | vm 200 on pve2\nstatus: running\nconfig:\n" + indent(fx.CONFIGS["200"]) +
                         "snapshots:\nvolumes:\n  scsi0 local-lvm vm-200-disk-0 32G\n")

    def test_output_is_deterministic(self):
        self.assertEqual(self.lab.run("pve-state", "101").stdout, self.lab.run("pve-state", "101").stdout)

    def test_unknown_guest_and_unreachable_node(self):
        missing = self.lab.run("pve-state", "999")
        self.assertEqual(missing.returncode, 1)
        self.lab.unreachable("pve1")
        result = self.lab.run("pve-state", "101")
        self.assertEqual(result.returncode, 1)
        self.assertIn("could not read: pve1", result.stderr)
        result = self.lab.run("pve-state", "pve1")
        self.assertEqual(result.returncode, 1)
        self.assertIn("No route to host; see docs/ssh-access.md", result.stderr)

    def test_empty_or_unparseable_guest_reads_fail(self):
        for command, stdout in (("pct status 101", ""), ("pct config 101", ""),
                                ("pct listsnapshot 101", "garbage\n")):
            with self.subTest(command=command):
                fx.load(self.lab)
                self.lab.respond("pve1", command, stdout=stdout)
                result = self.lab.run("pve-state", "101")
                self.assertEqual(result.returncode, 1, result.stdout)

    def test_a_failed_backup_read_fails(self):
        self.lab.respond("pve1", "pvesm list nas-backup --content backup", exit=255, stderr="ssh: connection lost\n")
        result = self.lab.run("pve-state", "101")
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("unavailable", result.stdout)
        self.assertIn("connection lost", result.stderr)

    def test_a_backup_storage_restricted_to_other_nodes_is_unavailable_here(self):
        # pvesm status lists only the storages enabled for this node
        status = "".join(line + "\n" for line in fx.pvesm_status().splitlines() if not line.startswith("nas-backup"))
        self.lab.respond("pve1", "pvesm status", stdout=status)
        result = self.lab.run("pve-state", "101")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.endswith("backups on nas-backup:\n  unavailable on pve1\n"))
        self.assertNotIn("pvesm list nas-backup --content backup", self.lab.commands("collect"))

    def test_an_inactive_or_disabled_backup_storage_is_unavailable_not_a_failure(self):
        # an outage of the backup storage must not block baselines of every guest
        for state in ("inactive", "disabled"):
            with self.subTest(state=state):
                fx.load(self.lab)
                status = fx.pvesm_status().replace("nfs     active", f"nfs   {state}")
                self.lab.respond("pve1", "pvesm status", stdout=status)
                self.lab.respond("pve1", "pvesm list nas-backup --content backup", exit=255,
                                 stderr="storage 'nas-backup' is not online\n")
                result = self.lab.run("pve-state", "101")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue(result.stdout.endswith(f"backups on nas-backup:\n  unavailable on pve1 (storage {state})\n"),
                                result.stdout)

    def test_usage_errors(self):
        self.assertEqual(self.lab.run("pve-state").returncode, 2)
        self.assertEqual(self.lab.run("pve-state", "101", "102").returncode, 2)
        unknown = self.lab.run("pve-state", "pve9")
        self.assertEqual(unknown.returncode, 2)
        self.assertIn("unknown node 'pve9'", unknown.stderr)
        self.assertEqual(self.lab.run("pve-state", "--dryrun").returncode, 2)
        self.assertEqual(self.lab.run("pve-state", "--help").returncode, 0)


class NodeStateTest(unittest.TestCase):
    def node_state(self, version: str, **overrides):
        lab = Lab()
        self.addCleanup(lab.close)
        fx.load(lab, version)
        for command, answer in overrides.items():
            lab.responses["pve1"][command] = answer
        result = lab.run("pve-state", "pve1")
        self.assertEqual(result.returncode, 0, result.stderr)
        return lab, result.stdout

    def test_node_on_pve8(self):
        lab, out = self.node_state("8")
        v = fx.VERSIONS["8"]
        self.assertTrue(out.startswith("pve-state 1 | node pve1\npackages:\n  proxmox-ve: 8.4.0"))
        for line in (f"kernel running: {v['kernel']}\n", f"kernel newest: {v['newer']}\n",
                     "storages:\n  local dir active\n  local-lvm lvmthin active\n  nas-backup nfs active\n",
                     "quorum: expected 2, total 2, quorate Yes\nmembers: pve1 pve2\n",
                     "upgradable:\n  proxmox-kernel-6.8 6.8.12-10 6.8.12-11\n  pve-manager 8.4.1 8.4.2\n",
                     "apt sources:\n  /etc/apt/sources.list:\n    deb http://deb.debian.org/debian bookworm main contrib\n",
                     "  /etc/apt/sources.list.d/pve-enterprise.list:\n"
                     "    deb https://enterprise.proxmox.com/debian/pve bookworm pve-enterprise\n"):
            self.assertIn(line, out)
        self.assertEqual(lab.commands("admin"), [])

    def test_node_on_pve9(self):
        _, out = self.node_state("9")
        self.assertIn("kernel newest: 6.14.11-4-pve\n", out)
        self.assertNotIn("/etc/apt/sources.list:\n", out)
        self.assertIn("  /etc/apt/sources.list.d/pve-enterprise.sources:\n    Types: deb\n"
                      "    URIs: https://enterprise.proxmox.com/debian/pve\n", out)

    def test_standalone_node(self):
        _, out = self.node_state("8", **{"cat /etc/pve/corosync.conf": fx.COROSYNC_ABSENT,
                                         "pvecm status": fx.STANDALONE, "pvecm nodes": fx.STANDALONE})
        self.assertIn("quorum: standalone\n", out)
        self.assertNotIn("members:", out)

    def test_a_cluster_file_system_that_is_down_is_not_standalone(self):
        for answer in (fx.PMXCFS_DOWN_NODES, fx.ok("")):
            with self.subTest(answer=answer):
                lab = Lab()
                self.addCleanup(lab.close)
                fx.load(lab)
                fx.pmxcfs_down(lab, "pve1")
                lab.respond("pve1", "ls /etc/pve/nodes", **answer)
                result = lab.run("pve-state", "pve1")
                self.assertEqual(result.returncode, 1)
                self.assertNotIn("standalone", result.stdout)
                self.assertIn("could not read the quorum of pve1 (/etc/pve/nodes, exit "
                              f"{answer['exit']})", result.stderr)

    def test_a_cluster_that_is_not_quorate_is_not_standalone(self):
        _, out = self.node_state("8", **{"pvecm status": fx.PVECM_NOT_QUORATE})
        self.assertIn("quorum: expected 2, total 1, quorate No\nmembers: pve1 pve2\n", out)
        self.assertNotIn("standalone", out)

    def test_corosync_down_or_unreadable_corosync_conf_fails(self):
        for command, answer in (("pvecm status", fx.PVECM_COROSYNC_DOWN),
                                ("pvecm status", fx.ok("garbage\n")),
                                ("cat /etc/pve/corosync.conf", {"stdout": "", "exit": 126,
                                 "stderr": "homelab-collect: refused: cat /etc/pve/corosync.conf\n"})):
            with self.subTest(command=command, answer=answer):
                lab = Lab()
                self.addCleanup(lab.close)
                fx.load(lab)
                lab.respond("pve1", command, **answer)
                result = lab.run("pve-state", "pve1")
                self.assertEqual(result.returncode, 1)
                self.assertNotIn("standalone", result.stdout)

    def test_empty_or_unparseable_node_reads_fail(self):
        for command, answer in (("ls /boot", fx.ok("efi\ngrub\n")), ("pveversion -v", fx.ok("")),
                                ("uname -r", fx.ok("")), ("pvesm status", fx.ok("")),
                                ("cat /etc/apt/sources.list", {"stdout": "", "exit": 255, "stderr": "ssh: boom\n"}),
                                ("cat /etc/apt/sources.list", {"stdout": "", "exit": 126,
                                 "stderr": "homelab-collect: refused: cat /etc/apt/sources.list\n"})):
            with self.subTest(command=command, answer=answer):
                lab = Lab()
                self.addCleanup(lab.close)
                fx.load(lab)
                lab.respond_seq("pve1", command, *([fx.ok("6.8.12-10-pve\n")] if command == "uname -r" else []), answer)
                result = lab.run("pve-state", "pve1")
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertNotIn("kernel newest: \n", result.stdout)

    def test_dropped_connection_on_quorum_is_not_standalone(self):
        lab = Lab()
        self.addCleanup(lab.close)
        fx.load(lab)
        lab.respond("pve1", "pvecm status", exit=255, stderr="Connection closed\n")
        result = lab.run("pve-state", "pve1")
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("standalone", result.stdout)
        self.assertIn("Connection closed", result.stderr)

    def test_failed_upgradable_read_fails(self):
        lab = Lab()
        self.addCleanup(lab.close)
        fx.load(lab)
        lab.respond("pve1", "apt list --upgradable", exit=255, stderr="Connection closed\n")
        result = lab.run("pve-state", "pve1")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Connection closed", result.stderr)

    def test_unreachable_node(self):
        lab = Lab()
        self.addCleanup(lab.close)
        fx.load(lab)
        lab.unreachable("pve1")
        result = lab.run("pve-state", "pve1")
        self.assertEqual(result.returncode, 1)
        self.assertIn("node pve1 is unreachable", result.stderr)


if __name__ == "__main__":
    unittest.main()
