import unittest

from tests import pvefixtures as fx
from tests.toolkit import Lab

AUTOREMOVE = "env DEBIAN_FRONTEND=noninteractive apt-get -y autoremove"
FAST_STATUS = "fast           lvmthin     active       500000000        10000000       490000000    2.00%\n"
FAST_CFG = "\nlvmthin: fast\n\tthinpool fast\n\tvgname ssd\n\tcontent rootdir,images\n"


def df(avail: int) -> str:
    return ("Filesystem              1-blocks        Used   Available Capacity Mounted on\n"
            f"/dev/mapper/pve-root 101203873792 13435469824 {avail}      14% /\n")


class CleanupTest(unittest.TestCase):
    def setUp(self):
        self.lab = Lab()
        self.addCleanup(self.lab.close)
        fx.load(self.lab)

    def test_node_dry_run_and_yes(self):
        dry = self.lab.run("pve-cleanup", "pve1", "--dry-run")
        self.assertIn(f"step 1/2: ssh pve1-admin -- {AUTOREMOVE}\nstep 2/2: ssh pve1-admin -- apt-get clean\n",
                      dry.stdout)
        self.assertEqual(self.lab.commands("admin"), [])
        self.lab.respond("pve1", AUTOREMOVE)
        self.lab.respond("pve1", "apt-get clean")
        self.lab.respond_seq("pve1", "df -P -B1 /", {"stdout": df(82580643840)}, {"stdout": df(83654385664)})
        result = self.lab.run("pve-cleanup", "pve1", "--yes")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.endswith("verify: 1.00 GiB freed on /: ok\n"))

    def test_container(self):
        dry = self.lab.run("pve-cleanup", "101", "--dry-run")
        self.assertIn(f"step 1/2: ssh pve1-admin -- pct exec 101 -- {AUTOREMOVE}\n"
                      "step 2/2: ssh pve1-admin -- pct exec 101 -- apt-get clean\n", dry.stdout)
        vm = self.lab.run("pve-cleanup", "200", "--dry-run")
        self.assertEqual(vm.returncode, 1)
        self.assertIn("200 is a VM", vm.stdout)

    def test_failed_step_stops_and_no_verify(self):
        self.lab.respond("pve1", AUTOREMOVE, exit=255, stderr="ssh: Broken pipe\n")
        self.lab.respond("pve1", "apt-get clean")
        result = self.lab.run("pve-cleanup", "pve1", "--yes")
        self.assertEqual(result.returncode, 1)
        self.assertIn("result: exit 255\n", result.stdout)
        self.assertNotIn("verify:", result.stdout)
        self.assertEqual(self.lab.commands("admin"), [AUTOREMOVE])

    def test_container_step_failure_has_no_verify(self):
        self.lab.respond("pve1", f"pct exec 101 -- {AUTOREMOVE}", exit=1)
        result = self.lab.run("pve-cleanup", "101", "--yes")
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("verify:", result.stdout)
        self.assertEqual(len(self.lab.commands("admin")), 1)

    def test_without_yes_and_terminal_nothing_runs(self):
        result = self.lab.run("pve-cleanup", "pve1")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.lab.commands("admin"), [])

    def test_leftover_option_is_a_usage_error(self):
        result = self.lab.run("pve-cleanup", "pve1", "--dryrun")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.lab.commands("admin"), [])

    def test_unreadable_free_space_fails_the_check(self):
        self.lab.respond("pve1", "df -P -B1 /", exit=255, stderr="ssh: boom\n")
        result = self.lab.run("pve-cleanup", "pve1", "--yes")
        self.assertEqual(result.returncode, 1)
        self.assertIn("cannot read the free space of / on pve1: FAILED", result.stdout)
        self.assertEqual(self.lab.commands("admin"), [])

    def test_empty_free_space_fails_the_check(self):
        self.lab.respond("pve1", "df -P -B1 /", stdout="")
        result = self.lab.run("pve-cleanup", "pve1", "--yes")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.lab.commands("admin"), [])

    def test_unreadable_free_space_after_fails_the_verify(self):
        self.lab.respond("pve1", AUTOREMOVE)
        self.lab.respond("pve1", "apt-get clean")
        self.lab.respond_seq("pve1", "df -P -B1 /", {"stdout": df(82580643840)}, {"stdout": "", "exit": 255})
        result = self.lab.run("pve-cleanup", "pve1", "--yes")
        self.assertEqual(result.returncode, 1)
        self.assertIn("after the cleanup: FAILED", result.stdout)

    def sim(self, removals, summary=None):
        lines = "".join(f"Remv {name} [1.0]\n" for name in removals)
        summary = summary or f"0 upgraded, 0 newly installed, {len(removals)} to remove and 0 not upgraded.\n"
        return "Reading package lists...\n" + summary + lines

    def test_removal_of_the_stack_is_refused(self):
        for name in ("pve-manager", "proxmox-ve", "qemu-server", "pve-container"):
            self.lab.respond("pve1", "apt-get -s autoremove", stdout=self.sim(["libfoo", name]))
            result = self.lab.run("pve-cleanup", "pve1", "--yes")
            self.assertEqual(result.returncode, 1, name)
            self.assertIn("would remove part of the Proxmox stack", result.stdout)
            self.assertEqual(self.lab.commands("admin"), [])

    def test_removal_guard_messages_name_the_simulation(self):
        self.lab.respond("pve1", "apt-get -s autoremove", stdout=self.sim(["proxmox-ve"]))
        result = self.lab.run("pve-cleanup", "pve1", "--yes")
        self.assertIn("check: the autoremove simulation on pve1 would remove part of the Proxmox stack (proxmox-ve): "
                      "do not run it: FAILED\n", result.stdout)

    def test_removal_of_the_running_kernel_is_refused(self):
        for name in ("proxmox-kernel-6.8.12-10-pve", "proxmox-kernel-6.8.12-10-pve-signed", "pve-kernel-6.8.12-10-pve"):
            self.lab.respond("pve1", "apt-get -s autoremove", stdout=self.sim([name]))
            result = self.lab.run("pve-cleanup", "pve1", "--yes")
            self.assertEqual(result.returncode, 1, name)
            self.assertIn("would remove the running kernel 6.8.12-10-pve", result.stdout)
            self.assertEqual(self.lab.commands("admin"), [])

    def test_unreadable_or_unparseable_simulation_is_refused(self):
        bad = [{"exit": 255, "stderr": "boom\n"}, {"exit": 126, "stderr": "homelab-collect: refused: x\n"},
               {"stdout": ""}, {"stdout": "Reading package lists...\n"}]
        for answer in bad:
            self.lab.respond("pve1", "apt-get -s autoremove", **answer)
            result = self.lab.run("pve-cleanup", "pve1", "--yes")
            self.assertEqual(result.returncode, 1, answer)
            self.assertIn("autoremove simulation", result.stdout)
            self.assertEqual(self.lab.commands("admin"), [])

    def test_summary_count_must_match_the_listed_removals(self):
        summary = "0 upgraded, 0 newly installed, 2 to remove and 0 not upgraded.\n"
        self.lab.respond("pve1", "apt-get -s autoremove", stdout=self.sim(["libfoo"], summary=summary))
        result = self.lab.run("pve-cleanup", "pve1", "--yes")
        self.assertEqual(result.returncode, 1)
        self.assertIn("check: the autoremove simulation on pve1 states 2 package(s) to remove but lists 1", result.stdout)
        self.assertIn("FAILED", result.stdout)
        self.assertEqual(self.lab.commands("admin"), [])

    def test_unreadable_running_kernel_is_refused(self):
        self.lab.respond("pve1", "uname -r", exit=255, stderr="boom\n")
        result = self.lab.run("pve-cleanup", "pve1", "--yes")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.lab.commands("admin"), [])

    def test_removal_list_is_shown_in_dry_run(self):
        result = self.lab.run("pve-cleanup", "pve1", "--dry-run")
        self.assertIn("check: the autoremove would remove 1 package(s): proxmox-kernel-6.8.12-8-pve-signed: ok\n",
                      result.stdout)
        self.lab.respond("pve1", "apt-get -s autoremove", stdout=self.sim([]))
        result = self.lab.run("pve-cleanup", "pve1", "--dry-run")
        self.assertIn("check: the autoremove simulation removes no package: ok\n", result.stdout)
        self.assertIn("apt-get clean\n", result.stdout)

    def test_no_space_freed_is_reported_honestly(self):
        self.lab.respond("pve1", AUTOREMOVE)
        self.lab.respond("pve1", "apt-get clean")
        self.lab.respond_seq("pve1", "df -P -B1 /", {"stdout": df(83654385664)}, {"stdout": df(82580643840)})
        result = self.lab.run("pve-cleanup", "pve1", "--yes")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.endswith(
            "verify: no space freed on / (1.00 GiB used by other activity meanwhile): ok\n"))

    def test_container_must_be_running(self):
        self.lab.respond("pve1", "pct status 101", stdout="status: stopped\n")
        result = self.lab.run("pve-cleanup", "101", "--dry-run")
        self.assertEqual(result.returncode, 1)
        self.assertIn("ct 101 is stopped: start it first: FAILED", result.stdout)

    def test_container_must_use_apt(self):
        self.lab.respond("pve1", "pct config 101", stdout=fx.CONFIGS["101"].replace("ostype: debian", "ostype: alpine"))
        result = self.lab.run("pve-cleanup", "101", "--dry-run")
        self.assertEqual(result.returncode, 1)
        self.assertIn("ct 101 runs 'alpine': apt only: FAILED", result.stdout)


class MoveDiskTest(unittest.TestCase):
    def setUp(self):
        self.lab = Lab()
        self.addCleanup(self.lab.close)
        fx.load(self.lab)
        for node in ("pve1", "pve2"):
            self.lab.responses[node]["pvesm status"]["stdout"] += FAST_STATUS
            self.lab.responses[node]["cat /etc/pve/storage.cfg"]["stdout"] += FAST_CFG

    def test_container_dry_run_stops_moves_and_starts(self):
        result = self.lab.run("pve-move-disk", "101", "fast", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("check: rootfs of ct 101 is local-lvm:vm-101-disk-0 (8G): ok\n", result.stdout)
        self.assertIn("step 1/3: ssh pve1-admin -- pct shutdown 101 --timeout 120\n"
                      "step 2/3: ssh pve1-admin -- pct move-volume 101 rootfs fast\n"
                      "step 3/3: ssh pve1-admin -- pct start 101\n", result.stdout)
        self.assertIn("rollback: the source volume stays in the config as an unused disk on local-lvm", result.stdout)
        self.assertEqual(self.lab.commands("admin"), [])

    def test_vm_moves_online_and_delete_source(self):
        result = self.lab.run("pve-move-disk", "200", "fast", "--delete-source", "--dry-run")
        self.assertIn("step 1/1: ssh pve2-admin -- qm disk move 200 scsi0 fast --delete 1\n", result.stdout)
        self.assertIn("rollback: none: --delete-source removes the source volume; take bin/pve-backup 200 first",
                      result.stdout)

    def test_pre_checks(self):
        same = self.lab.run("pve-move-disk", "101", "local-lvm", "--dry-run")
        self.assertEqual((same.returncode, same.stdout.strip()), (0, "already on local-lvm: nothing to do"))
        backup = self.lab.run("pve-move-disk", "101", "nas-backup", "--dry-run")
        self.assertEqual(backup.returncode, 1)
        self.assertIn("storage nas-backup does not accept rootdir", backup.stdout)
        self.lab.responses["pve1"]["pvesm status"]["stdout"] = fx.pvesm_status() + FAST_STATUS.replace(
            "490000000", "1000")
        small = self.lab.run("pve-move-disk", "101", "fast", "--dry-run")
        self.assertEqual(small.returncode, 1)
        self.assertIn("storage fast has 0.00 GiB free; rootfs needs 8.00 GiB", small.stdout)
        missing = self.lab.run("pve-move-disk", "101", "fast", "--volume", "mp3", "--dry-run")
        self.assertIn("ct 101 has no volume mp3", missing.stdout)

    def test_yes_moves_and_verifies(self):
        for command in ("pct shutdown 101 --timeout 120", "pct move-volume 101 rootfs fast", "pct start 101"):
            self.lab.respond("pve1", command)
        moved = fx.CONFIGS["101"].replace("rootfs: local-lvm:vm-101-disk-0,size=8G",
                                          "rootfs: fast:vm-101-disk-0,size=8G\nunused0: local-lvm:vm-101-disk-0")
        self.lab.respond_seq("pve1", "pct config 101", {"stdout": fx.CONFIGS["101"]}, {"stdout": moved})
        result = self.lab.run("pve-move-disk", "101", "fast", "--yes")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.endswith("verify: rootfs of ct 101 is on fast: ok\nverify: ct 101 is running: ok\n"))

    def test_verification_catches_a_move_that_did_not_happen(self):
        for command in ("pct shutdown 101 --timeout 120", "pct move-volume 101 rootfs fast", "pct start 101"):
            self.lab.respond("pve1", command)
        result = self.lab.run("pve-move-disk", "101", "fast", "--yes")
        self.assertEqual(result.returncode, 1)
        self.assertIn("verify: rootfs of ct 101 is still on local-lvm: FAILED", result.stdout)

    def test_failed_step_stops_the_plan(self):
        self.lab.respond("pve1", "pct shutdown 101 --timeout 120", exit=255, stderr="ssh: Broken pipe\n")
        self.lab.respond("pve1", "pct move-volume 101 rootfs fast")
        result = self.lab.run("pve-move-disk", "101", "fast", "--yes")
        self.assertEqual(result.returncode, 1)
        self.assertIn("result: exit 255\n", result.stdout)
        self.assertNotIn("verify:", result.stdout)
        self.assertEqual(self.lab.commands("admin"), ["pct shutdown 101 --timeout 120"])

    def test_without_yes_and_terminal_nothing_runs(self):
        result = self.lab.run("pve-move-disk", "101", "fast")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.lab.commands("admin"), [])

    def test_leftover_option_is_a_usage_error(self):
        result = self.lab.run("pve-move-disk", "101", "fast", "--dryrun")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.lab.commands("admin"), [])

    def test_stopped_container_is_not_shut_down_or_started(self):
        self.lab.respond("pve1", "pct status 101", stdout="status: stopped\n")
        result = self.lab.run("pve-move-disk", "101", "fast", "--dry-run")
        self.assertIn("step 1/1: ssh pve1-admin -- pct move-volume 101 rootfs fast\n", result.stdout)
        self.assertNotIn("pct shutdown", result.stdout)
        self.assertNotIn("pct start", result.stdout)

    def test_vm_default_volume_is_scsi0_without_delete(self):
        result = self.lab.run("pve-move-disk", "200", "fast", "--dry-run")
        self.assertIn("step 1/1: ssh pve2-admin -- qm disk move 200 scsi0 fast\n", result.stdout)

    def test_empty_config_fails_the_check(self):
        self.lab.respond("pve1", "pct config 101", stdout="")
        result = self.lab.run("pve-move-disk", "101", "fast", "--dry-run")
        self.assertEqual(result.returncode, 1)
        self.assertIn("empty answer: FAILED", result.stdout)

    def test_unreadable_status_fails_the_check(self):
        self.lab.respond("pve1", "pct status 101", exit=255, stderr="ssh: boom\n")
        result = self.lab.run("pve-move-disk", "101", "fast", "--dry-run")
        self.assertEqual(result.returncode, 1)
        self.assertIn("cannot read the status of ct 101: FAILED", result.stdout)

    def test_empty_status_fails_the_check(self):
        self.lab.respond("pve1", "pct status 101", stdout="")
        result = self.lab.run("pve-move-disk", "101", "fast", "--dry-run")
        self.assertEqual(result.returncode, 1)
        self.assertIn("cannot read the status of ct 101: empty answer: FAILED", result.stdout)

    def test_container_not_running_after_the_move_fails_the_verify(self):
        for command in ("pct shutdown 101 --timeout 120", "pct move-volume 101 rootfs fast", "pct start 101"):
            self.lab.respond("pve1", command)
        moved = fx.CONFIGS["101"].replace("rootfs: local-lvm:vm-101-disk-0,size=8G", "rootfs: fast:vm-101-disk-0,size=8G")
        self.lab.respond_seq("pve1", "pct config 101", {"stdout": fx.CONFIGS["101"]}, {"stdout": moved})
        self.lab.respond_seq("pve1", "pct status 101", {"stdout": "status: running\n"}, {"stdout": "status: stopped\n"})
        result = self.lab.run("pve-move-disk", "101", "fast", "--yes")
        self.assertEqual(result.returncode, 1)
        self.assertIn("verify: ct 101 is stopped after the move: FAILED", result.stdout)

    def test_delete_source_refused_with_snapshots(self):
        result = self.lab.run("pve-move-disk", "101", "fast", "--delete-source", "--yes")
        self.assertEqual(result.returncode, 1)
        self.assertIn("ct 101 has snapshots: --delete-source is refused", result.stdout)
        self.assertEqual(self.lab.commands("admin"), [])

    def test_locked_guest_is_refused(self):
        self.lab.respond("pve1", "pct config 101", stdout=fx.CONFIGS["101"] + "lock: backup\n")
        result = self.lab.run("pve-move-disk", "101", "fast", "--yes")
        self.assertEqual(result.returncode, 1)
        self.assertIn("ct 101 is locked (backup): the move would fail: FAILED", result.stdout)
        self.assertEqual(self.lab.commands("admin"), [])
        self.lab.respond("pve2", "qm config 200", stdout=fx.CONFIGS["200"] + "lock: migrate\n")
        vm = self.lab.run("pve-move-disk", "200", "fast", "--yes")
        self.assertEqual(vm.returncode, 1)
        self.assertEqual(self.lab.commands("admin"), [])

    def test_failed_move_restarts_the_container(self):
        self.lab.respond("pve1", "pct shutdown 101 --timeout 120")
        self.lab.respond("pve1", "pct move-volume 101 rootfs fast", exit=255, stderr="boom\n")
        self.lab.respond("pve1", "pct start 101")
        self.lab.respond_seq("pve1", "pct status 101", {"stdout": "status: running\n"},
                             {"stdout": "status: stopped\n"})
        result = self.lab.run("pve-move-disk", "101", "fast", "--yes")
        self.assertEqual(result.returncode, 1)
        self.assertIn("recovery: ssh pve1-admin -- pct start 101\nresult: exit 0\n"
                      "ct 101 is running again; the move did not complete\n", result.stdout)
        self.assertEqual(self.lab.commands("admin")[-1], "pct start 101")
        self.assertNotIn("verify:", result.stdout)

    def test_failed_recovery_says_the_container_is_stopped(self):
        self.lab.respond("pve1", "pct shutdown 101 --timeout 120")
        self.lab.respond("pve1", "pct move-volume 101 rootfs fast", exit=255, stderr="boom\n")
        self.lab.respond("pve1", "pct start 101", exit=255, stderr="boom\n")
        self.lab.respond_seq("pve1", "pct status 101", {"stdout": "status: running\n"},
                             {"stdout": "status: stopped\n"})
        result = self.lab.run("pve-move-disk", "101", "fast", "--yes")
        self.assertEqual(result.returncode, 1)
        self.assertIn("ct 101 was shut down and is still stopped: pct start 101\n", result.stdout)

    def test_stopped_container_is_not_started_after_a_failed_move(self):
        self.lab.respond("pve1", "pct status 101", stdout="status: stopped\n")
        self.lab.respond("pve1", "pct move-volume 101 rootfs fast", exit=255, stderr="boom\n")
        result = self.lab.run("pve-move-disk", "101", "fast", "--yes")
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("recovery:", result.stdout)
        self.assertEqual(self.lab.commands("admin"), ["pct move-volume 101 rootfs fast"])

    def test_declined_confirmation_does_not_start_the_container(self):
        self.lab.respond_seq("pve1", "pct status 101", {"stdout": "status: running\n"},
                             {"stdout": "status: stopped\n"})
        result = self.lab.run_tty(["bash", str(self.lab.root / "bin" / "pve-move-disk"), "101", "fast"], "n\n")
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("recovery:", result.stdout)
        self.assertEqual(self.lab.commands("admin"), [])

    def test_unreadable_status_after_a_failed_move_sends_no_start(self):
        self.lab.respond("pve1", "pct shutdown 101 --timeout 120")
        self.lab.respond("pve1", "pct move-volume 101 rootfs fast", exit=255, stderr="boom\n")
        self.lab.respond_seq("pve1", "pct status 101", {"stdout": "status: running\n"},
                             {"exit": 255, "stderr": "boom\n"})
        result = self.lab.run("pve-move-disk", "101", "fast", "--yes")
        self.assertEqual(result.returncode, 1)
        self.assertIn("ct 101 state is unknown (status could not be read); check it and run pct start 101 "
                      "if it is stopped\n", result.stdout)
        self.assertNotIn("recovery:", result.stdout)
        self.assertNotIn("pct start 101", self.lab.commands("admin"))

    def test_failed_start_step_is_not_retried(self):
        for command in ("pct shutdown 101 --timeout 120", "pct move-volume 101 rootfs fast"):
            self.lab.respond("pve1", command)
        self.lab.respond("pve1", "pct start 101", exit=1)
        self.lab.respond_seq("pve1", "pct status 101", {"stdout": "status: running\n"},
                             {"stdout": "status: stopped\n"})
        result = self.lab.run("pve-move-disk", "101", "fast", "--yes")
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("recovery:", result.stdout)
        self.assertEqual(self.lab.commands("admin").count("pct start 101"), 1)

    def test_cancelled_run_sends_nothing(self):
        result = self.lab.run_tty(["bash", str(self.lab.root / "bin" / "pve-move-disk"), "101", "fast"], "n\n")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.lab.commands("admin"), [])

    def test_source_pool_above_95_percent_warns(self):
        status = fx.pvesm_status().replace("27.35%", "96.10%") + FAST_STATUS
        self.lab.responses["pve1"]["pvesm status"]["stdout"] = status
        result = self.lab.run("pve-move-disk", "101", "fast", "--dry-run")
        self.assertIn("check: the source storage local-lvm is at 96.10%: the move may fail", result.stdout)
        self.assertEqual(result.returncode, 0)
        quiet = self.lab.run("pve-move-disk", "200", "fast", "--dry-run")
        self.assertNotIn("the source storage", quiet.stdout)

    def test_unreadable_target_free_space_fails_the_check(self):
        self.lab.responses["pve1"]["pvesm status"]["stdout"] = fx.pvesm_status() + FAST_STATUS.replace(
            "490000000", "-")
        result = self.lab.run("pve-move-disk", "101", "fast", "--dry-run")
        self.assertEqual(result.returncode, 1)
        self.assertIn("cannot read the free space of storage fast: FAILED", result.stdout)


if __name__ == "__main__":
    unittest.main()
