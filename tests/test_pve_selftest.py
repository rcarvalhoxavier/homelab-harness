import unittest

from tests import pvefixtures as fx
from tests.toolkit import Lab

PIHOLE_STATUS = "  [✓] FTL is listening on port 53\n     [✓] UDP (IPv4)\n"


class SelftestTest(unittest.TestCase):
    def setUp(self):
        self.lab = Lab()
        self.addCleanup(self.lab.close)
        fx.load(self.lab)

    def test_a_correct_installation_passes(self):
        result = self.lab.run("pve-selftest")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        digest = fx.collect_hash(self.lab.root)
        self.assertEqual(result.stdout,
                         "pve-selftest 1\nPASS configuration: inventory/nodes loads (2 nodes); no .env.local, defaults apply\n" +
                         "".join(f"PASS {node}: the collect alias connects\n"
                                 f"PASS {node}: Proxmox VE 8 (pve-manager/8.4.1)\n"
                                 f"PASS {node}: the dispatcher matches the repo ({digest})\n"
                                 f"PASS {node}: the collect key is restricted (id was refused)\n"
                                 f"PASS {node}: pvesm status parses (7 fields, active storages within 0-100%)\n"
                                 f"PASS {node}: pvecm status parses (2 of 2 votes, quorate Yes)\n"
                                 f"PASS {node}: thin pools parse (data and metadata within 0-100%)\n"
                                 for node in ("pve1", "pve2")) +
                         "summary: 15 passed, 0 failed, 0 warnings, 0 skipped\n")
        self.assertEqual(self.lab.commands("admin"), [])

    def test_an_unreachable_node_shows_why_and_where_to_look(self):
        self.lab.unreachable("pve2")
        result = self.lab.run("pve-selftest", "--node", "pve2")
        self.assertEqual(result.returncode, 1)
        self.assertIn("FAIL pve2: the collect alias does not connect (uname -r, exit 255): ssh: connect to host "
                      "pve2 port 22: No route to host; see docs/ssh-access.md\n", result.stdout)
        self.assertEqual(result.stderr.count("No route to host"), 0, result.stderr)

    def test_the_configuration_line_names_env_local_only_when_it_exists(self):
        self.lab.write_env("PVE_BACKUP_STORAGE=nas-backup\n")
        result = self.lab.run("pve-selftest", "--node", "pve1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS configuration: .env.local and inventory/nodes load (2 nodes)\n", result.stdout)
        self.assertNotIn("no .env.local", result.stdout)

    def test_proxmox_ve_9_is_experimental_and_other_versions_fail(self):
        lab = Lab()
        self.addCleanup(lab.close)
        fx.load(lab, "9")
        result = lab.run("pve-selftest", "--node", "pve1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("WARN pve1: Proxmox VE 9 support is experimental (not yet verified on a real node): run --simulate and --dry-run before any change\n", result.stdout)
        for answer, line in ((fx.ok("pve-manager/7.4.3/9002ab8a (running kernel: 5.15.108-1-pve)\n"),
                              "FAIL pve1: unsupported Proxmox VE version: pve-manager/7.4.3/9002ab8a\n"),
                             ({"stdout": "", "exit": 126, "stderr": "homelab-collect: refused: pveversion\n"},
                              "FAIL pve1: pveversion could not be read (exit 126)\n")):
            with self.subTest(line=line):
                self.lab.respond("pve1", "pveversion", **answer)
                result = self.lab.run("pve-selftest", "--node", "pve1")
                self.assertEqual(result.returncode, 1)
                self.assertIn(line, result.stdout)

    def test_an_unrestricted_key_fails(self):
        self.lab.unrestricted("pve1")
        self.lab.respond("pve1", "id", stdout="uid=0(root) gid=0(root) groups=0(root)\n")
        result = self.lab.run("pve-selftest", "--node", "pve1")
        self.assertEqual(result.returncode, 1)
        self.assertIn("FAIL pve1: the collect key is not restricted (id ran)", result.stdout)

    def test_dispatcher_version(self):
        self.lab.respond("pve1", "homelab-collect --version", stdout="homelab-collect 0000000000000000\n")
        self.lab.respond("pve2", "homelab-collect --version", exit=127,
                         stderr="bash: line 1: homelab-collect: command not found\n")
        result = self.lab.run("pve-selftest")
        self.assertEqual(result.returncode, 0)
        self.assertIn("WARN pve1: the dispatcher (0000000000000000) differs from the repo", result.stdout)
        self.assertIn("run bin/pve-collect-install pve1", result.stdout)
        self.assertIn("WARN pve2: no dispatcher answers", result.stdout)

    def test_refused_or_failed_reads_fail(self):
        self.lab.respond("pve1", "pvecm status", exit=126, stderr="homelab-collect: refused: pvecm status\n")
        self.lab.respond("pve2", "pvecm status", exit=255, stderr="ssh: connection lost\n")
        result = self.lab.run("pve-selftest")
        self.assertEqual(result.returncode, 1)
        self.assertIn("FAIL pve1: pvecm status could not be read (exit 126", result.stdout)
        self.assertIn("FAIL pve2: pvecm status could not be read (exit 255", result.stdout)
        self.assertNotIn("standalone", result.stdout)
        self.assertIn("refused", result.stderr)

    def test_refused_lvs_fails_and_empty_lvs_skips(self):
        lvs = ("lvs --noheadings --units b --nosuffix -o vg_name,lv_name,lv_size,data_percent,metadata_percent "
               "--select segtype=thin-pool")
        self.lab.respond("pve1", lvs, exit=126, stderr="homelab-collect: refused: lvs\n")
        self.lab.respond("pve2", lvs, stdout="")
        result = self.lab.run("pve-selftest")
        self.assertEqual(result.returncode, 1)
        self.assertIn("FAIL pve1: thin pools could not be read (exit 126", result.stdout)
        self.assertIn("SKIP pve2: thin pools (none found)", result.stdout)

    def test_an_inactive_thin_pool_warns_and_a_refused_pvesm_status_is_visible(self):
        lvs = ("lvs --noheadings --units b --nosuffix -o vg_name,lv_name,lv_size,data_percent,metadata_percent "
               "--select segtype=thin-pool")
        self.lab.respond("pve1", lvs, stdout="  pve data 374538764288\n")
        self.lab.respond("pve2", "pvesm status", exit=126, stderr="homelab-collect: refused: pvesm status\n")
        result = self.lab.run("pve-selftest")
        self.assertIn("WARN pve1: thin pool pve/data is inactive (usage not reported): "
                      "activate it with lvchange -ay pve/data\n", result.stdout)
        self.assertNotIn("FAIL pve1", result.stdout)
        self.assertIn("FAIL pve2: pvesm status could not be read or parsed", result.stdout)
        self.assertIn("refused by the host's dispatcher on pve2: 'pvesm status'", result.stderr)

    def test_example_collector_exits_1_on_a_failed_read(self):
        self.lab.install_lists(local=(self.lab.root / "examples" / "local" / "collect.allow").read_text())
        self.lab.respond("pve1", "pct exec 101 -- pihole -v", exit=255, stderr="ssh: connection lost\n")
        self.lab.respond("pve1", "pct exec 101 -- pihole status", stdout=PIHOLE_STATUS)
        state = self.lab.shell("bash examples/local/bin/pihole-state")
        self.assertEqual(state.returncode, 1, state.stdout + state.stderr)
        self.assertNotIn("status:", state.stdout)

    def test_password_fallback(self):
        self.lab.write_env("HOMELAB_SSHPASS=1\nSSHPASS=fallback-secret\n")
        result = self.lab.run("pve-selftest", "--node", "pve1")
        self.assertIn("WARN password fallback in use", result.stdout)
        self.assertIn("SKIP pve1: dispatcher checks (the password fallback has no forced command)", result.stdout)

    def test_quorum_not_quorate_parses_and_corosync_down_fails(self):
        self.lab.respond("pve1", "pvecm status", **fx.PVECM_NOT_QUORATE)
        self.lab.respond("pve2", "pvecm status", **fx.PVECM_COROSYNC_DOWN)
        result = self.lab.run("pve-selftest")
        self.assertEqual(result.returncode, 1)
        self.assertIn("PASS pve1: pvecm status parses (1 of 2 votes, quorate No)\n", result.stdout)
        self.assertIn("FAIL pve2: pvecm status output could not be parsed", result.stdout)
        self.assertNotIn("standalone", result.stdout)

    def test_a_cluster_file_system_that_is_down_fails(self):
        fx.pmxcfs_down(self.lab, "pve1")
        result = self.lab.run("pve-selftest", "--node", "pve1")
        self.assertEqual(result.returncode, 1)
        self.assertIn("FAIL pve1: /etc/pve/nodes could not be read (exit 2; see the message above)\n", result.stdout)
        self.assertNotIn("standalone", result.stdout)

    def test_standalone_and_admin(self):
        fx.standalone(self.lab, "pve1")
        self.lab.respond("pve1", "true")
        result = self.lab.run("pve-selftest", "--node", "pve1", "--admin")
        self.assertIn("SKIP pve1: pvecm status (standalone node)", result.stdout)
        self.assertIn("PASS pve1: the admin alias connects", result.stdout)
        self.assertEqual(self.lab.commands("admin"), ["true"])

    def test_instance_checks(self):
        script = "#!/usr/bin/env bash\n{}\n"
        self.lab.write_local("selftest.d/10-ok", script.format("echo fine"), executable=True)
        self.lab.write_local("selftest.d/20-fail", script.format("echo broken; exit 1"), executable=True)
        self.lab.write_local("selftest.d/30-skip", script.format("echo not here; exit 77"), executable=True)
        self.lab.write_local("selftest.d/40-slow", script.format("sleep 5"), executable=True)
        self.lab.write_local("selftest.d/50-ignored", script.format("exit 1"), executable=False)
        result = self.lab.run("pve-selftest", "--node", "pve1", PVE_SELFTEST_TIMEOUT="1")
        self.assertEqual(result.returncode, 1)
        for line in ("PASS local 10-ok: fine\n", "FAIL local 20-fail: broken\n", "SKIP local 30-skip: not here\n",
                     "FAIL local 40-slow: timed out after 1 s\n"):
            self.assertIn(line, result.stdout)
        self.assertNotIn("50-ignored", result.stdout)

    def test_the_example_extension(self):
        self.lab.install_lists(local=(self.lab.root / "examples" / "local" / "collect.allow").read_text())
        self.lab.respond("pve1", "pct exec 101 -- pihole status", stdout=PIHOLE_STATUS)
        self.lab.respond("pve1", "pct exec 101 -- pihole -v",
                         stdout="Core version is v6.1 (Latest: v6.1)\nFTL version is v6.2 (Latest: v6.2)\n")
        result = self.lab.run("pve-selftest", "--node", "pve1", "--local-dir", "examples/local")
        self.assertIn("PASS local 10-pihole-dns: pihole FTL listening in CT 101\n", result.stdout)
        state = self.lab.shell("bash examples/local/bin/pihole-state")
        self.assertEqual(state.returncode, 0, state.stderr)
        self.assertEqual(state.stdout, "pihole-state 1 | ct 101 on pve1\nversions:\n"
                                       "  Core version is v6.1 (Latest: v6.1)\n  FTL version is v6.2 (Latest: v6.2)\n"
                                       "status:\n    [✓] FTL is listening on port 53\n       [✓] UDP (IPv4)\n")


if __name__ == "__main__":
    unittest.main()
