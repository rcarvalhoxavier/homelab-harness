import unittest
from unittest import mock

from tests import pvefixtures as fx
from tests.toolkit import Lab

UPDATE = "env DEBIAN_FRONTEND=noninteractive apt-get update"
UPGRADE = ("env DEBIAN_FRONTEND=noninteractive apt-get -y -o Dpkg::Options::=--force-confdef "
           "-o Dpkg::Options::=--force-confold dist-upgrade")


class UpdateHostTest(unittest.TestCase):
    def setUp(self):
        self.lab = Lab()
        self.addCleanup(self.lab.close)
        fx.load(self.lab)

    def test_dry_run_warns_about_enterprise_repositories(self):
        result = self.lab.run("pve-update-host", "pve1", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("check: dpkg is not in use: ok\n", result.stdout)
        self.assertIn("check: enterprise repositories enabled (/etc/apt/sources.list.d/ceph.list "
                      "/etc/apt/sources.list.d/pve-enterprise.list)", result.stdout)
        self.assertIn("path: risky\n", result.stdout)
        self.assertIn(f"step 1/2: ssh pve1-admin -- {UPDATE}\n", result.stdout)
        self.assertIn("step 2/2: ssh pve1-admin -- env DEBIAN_FRONTEND=noninteractive apt-get -y -o "
                      "Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold dist-upgrade\n", result.stdout)
        self.assertEqual(self.lab.commands("admin"), [])

    def test_unread_apt_sources_never_report_no_enterprise_repository(self):
        self.lab.respond("pve1", "ls /etc/apt/sources.list.d", exit=255, stderr="ssh: connection lost\n")
        result = self.lab.run("pve-update-host", "pve1", "--dry-run")
        self.assertIn("check: could not read every APT source of pve1: WARNING\n", result.stdout)
        self.assertIn("check: cannot tell whether an enterprise repository is enabled: WARNING\n", result.stdout)
        self.assertNotIn("no enterprise repository enabled", result.stdout)
        self.assertEqual(self.lab.commands("admin"), [])

    def test_simulate_needs_no_yes_and_no_admin(self):
        result = self.lab.run("pve-update-host", "pve1", "--simulate")
        self.assertEqual(result.returncode, 0)
        self.assertIn("simulation: 2 packages would be upgraded or installed, 0 removed\n"
                      "Inst pve-manager [8.4.1] (8.4.2 Proxmox:8.4/stable [all])\n", result.stdout)
        self.assertEqual(self.lab.commands("admin"), [])

    def test_simulate_says_the_package_lists_were_not_refreshed(self):
        result = self.lab.run("pve-update-host", "pve1", "--simulate")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("note: apt-get update was not run: the simulation reads the package lists as last refreshed; the upgrade refreshes them first\n", result.stdout)
        self.assertNotIn("new kernel", result.stdout)

    def test_simulate_and_dry_run_name_a_new_kernel_and_the_reboot(self):
        self.lab.respond("pve1", "apt-get -s dist-upgrade", stdout=fx.APT_SIM_NEW_KERNEL)
        sim = self.lab.run("pve-update-host", "pve1", "--simulate")
        self.assertEqual(sim.returncode, 0, sim.stderr)
        self.assertIn("simulation: 2 packages would be upgraded or installed, 0 removed\n", sim.stdout)
        self.assertIn("note: the upgrade installs a new kernel (proxmox-kernel-6.8.12-11-pve-signed): it runs only after a reboot, a change of its own\n", sim.stdout)
        dry = self.lab.run("pve-update-host", "pve1", "--dry-run")
        self.assertEqual(dry.returncode, 0, dry.stderr)
        self.assertIn("note: the upgrade installs a new kernel (proxmox-kernel-6.8.12-11-pve-signed): it runs only after a reboot, a change of its own\n", dry.stdout)
        self.assertEqual(self.lab.commands("admin"), [])

    def test_busy_dpkg_stops(self):
        self.lab.respond("pve1", "fuser /var/lib/dpkg/lock-frontend", stdout=" 4242\n")
        result = self.lab.run("pve-update-host", "pve1", "--dry-run")
        self.assertEqual(result.returncode, 1)
        self.assertIn("dpkg is in use on pve1", result.stdout)

    def test_yes_upgrades_and_reports_the_kernel(self):
        self.lab.respond("pve1", UPDATE)
        self.lab.respond("pve1", UPGRADE)
        self.lab.respond("pve1", "apt-get -s dist-upgrade", stdout=fx.APT_SIM_NONE)
        result = self.lab.run("pve-update-host", "pve1", "--yes")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.endswith("verify: no package left to upgrade: ok\n"
                                               "reboot needed: running 6.8.12-10-pve, newest 6.8.12-11-pve\n"))
        self.assertEqual(self.lab.commands("admin"), [UPDATE, UPGRADE])

    def test_packages_left_fail_the_verification(self):
        self.lab.respond("pve1", UPDATE)
        self.lab.respond("pve1", UPGRADE)
        result = self.lab.run("pve-update-host", "pve1", "--yes")
        self.assertEqual(result.returncode, 1)
        self.assertIn("verify: 2 packages still pending: FAILED", result.stdout)

    def test_pve9_sources(self):
        lab = Lab()
        self.addCleanup(lab.close)
        fx.load(lab, "9")
        result = lab.run("pve-update-host", "pve1", "--dry-run")
        self.assertIn("/etc/apt/sources.list.d/pve-enterprise.sources", result.stdout)

    def test_leftover_option_is_a_usage_error(self):
        result = self.lab.run("pve-update-host", "pve1", "--dryrun")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.lab.commands("admin"), [])

    def test_without_yes_and_terminal_nothing_runs(self):
        result = self.lab.run("pve-update-host", "pve1")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.lab.commands("admin"), [])

    def test_a_failed_step_stops_the_tool(self):
        self.lab.respond("pve1", UPDATE, exit=255, stderr="ssh: connect to host pve1-admin port 22: Broken pipe\n")
        result = self.lab.run("pve-update-host", "pve1", "--yes")
        self.assertEqual(result.returncode, 1)
        self.assertIn("result: exit 255\n", result.stdout)
        self.assertNotIn("verify:", result.stdout)
        self.assertEqual(self.lab.commands("admin"), [UPDATE])

    def test_empty_pre_check_simulation_stops_before_anything_is_sent(self):
        self.lab.respond("pve1", "apt-get -s dist-upgrade", stdout="")
        result = self.lab.run("pve-update-host", "pve1", "--yes")
        self.assertEqual(result.returncode, 1)
        self.assertIn("pre-upgrade simulation on pve1 returned no summary line: FAILED", result.stdout)
        self.assertEqual(self.lab.commands("admin"), [])

    def test_simulate_lists_removals_and_warns(self):
        sim = fx.APT_SIM.replace("2 upgraded, 0 newly installed, 0 to remove", "2 upgraded, 0 newly installed, 1 to remove") \
            + "Remv proxmox-ve [8.4.0]\n"
        self.lab.respond("pve1", "apt-get -s dist-upgrade", stdout=sim)
        result = self.lab.run("pve-update-host", "pve1", "--simulate")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("simulation: 2 packages would be upgraded or installed, 1 removed\n", result.stdout)
        self.assertIn("Remv proxmox-ve [8.4.0]\n", result.stdout)
        self.assertIn("check: the upgrade would remove packages (proxmox-ve): WARNING\n", result.stdout)

    def test_removal_of_proxmox_ve_fails_the_pre_check(self):
        sim = fx.APT_SIM.replace("0 to remove", "1 to remove") + "Remv proxmox-ve [8.4.0]\n"
        self.lab.respond("pve1", "apt-get -s dist-upgrade", stdout=sim)
        result = self.lab.run("pve-update-host", "pve1", "--yes")
        self.assertEqual(result.returncode, 1)
        self.assertIn("the pre-upgrade simulation on pve1 would remove part of the Proxmox stack (proxmox-ve): "
                      "do not run it: FAILED", result.stdout)
        self.assertEqual(self.lab.commands("admin"), [])

    def test_other_removals_only_warn(self):
        sim = fx.APT_SIM.replace("0 to remove", "1 to remove") + "Remv libfoo [1.0]\n"
        self.lab.respond("pve1", "apt-get -s dist-upgrade", stdout=sim)
        result = self.lab.run("pve-update-host", "pve1", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("check: the upgrade would remove packages (libfoo): WARNING\n", result.stdout)

    def test_simulate_with_dry_run_is_a_usage_error(self):
        result = self.lab.run("pve-update-host", "pve1", "--simulate", "--dry-run")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.lab.calls(), [])

    def test_simulate_without_summary_fails(self):
        self.lab.respond("pve1", "apt-get -s dist-upgrade", stdout="garbage\n")
        result = self.lab.run("pve-update-host", "pve1", "--simulate")
        self.assertEqual(result.returncode, 1)
        self.assertIn("returned no summary line: FAILED", result.stdout)

    def test_garbage_simulation_does_not_pass_verify(self):
        self.lab.respond("pve1", UPDATE)
        self.lab.respond("pve1", UPGRADE)
        self.lab.respond_seq("pve1", "apt-get -s dist-upgrade", {"stdout": fx.APT_SIM_NONE}, {"stdout": fx.APT_SIM_NONE}, {"stdout": "garbage\n"})
        result = self.lab.run("pve-update-host", "pve1", "--yes")
        self.assertEqual(result.returncode, 1)
        self.assertIn("verify: the simulation after the upgrade returned no summary line: FAILED", result.stdout)

    def test_unreadable_dpkg_lock_fails(self):
        self.lab.respond("pve1", "fuser /var/lib/dpkg/lock-frontend", exit=255, stderr="boom\n")
        result = self.lab.run("pve-update-host", "pve1", "--dry-run")
        self.assertEqual(result.returncode, 1)
        self.assertIn("cannot check the dpkg lock on pve1 (exit 255): FAILED", result.stdout)

    def test_an_unexpected_dpkg_lock_exit_fails(self):
        # fuser missing on the node: the guard did not run, so the tool must not plan the upgrade
        self.lab.respond("pve1", "fuser /var/lib/dpkg/lock-frontend", exit=127, stderr="fuser: command not found\n")
        result = self.lab.run("pve-update-host", "pve1", "--dry-run")
        self.assertEqual(result.returncode, 1)
        self.assertIn("cannot check the dpkg lock on pve1 (exit 127): FAILED", result.stdout)
        self.assertNotIn("step 1/2", result.stdout)

    def _finish(self, **responses):
        self.lab.respond("pve1", UPDATE)
        self.lab.respond("pve1", UPGRADE)
        self.lab.respond_seq("pve1", "apt-get -s dist-upgrade", {"stdout": fx.APT_SIM_NONE}, {"stdout": fx.APT_SIM_NONE}, {"stdout": fx.APT_SIM_NONE})
        for command, kwargs in responses.items():
            self.lab.respond("pve1", command, **kwargs)
        return self.lab.run("pve-update-host", "pve1", "--yes")

    def test_reports_the_newest_kernel_running(self):
        self.lab.respond("pve1", "uname -r", stdout=fx.VERSIONS["8"]["newer"] + "\n")
        result = self._finish()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.endswith(f"kernel: running the newest ({fx.VERSIONS['8']['newer']})\n"))

    def test_unreadable_kernel_fails_verify(self):
        # reachability probe, the removal guard of both simulations, then the verification
        kernel = {"stdout": fx.VERSIONS["8"]["kernel"] + "\n"}
        self.lab.respond_seq("pve1", "uname -r", kernel, kernel, kernel, {"stdout": ""})
        result = self._finish()
        self.assertEqual(result.returncode, 1)
        self.assertIn("verify: cannot read the running kernel of pve1: empty answer: FAILED", result.stdout)

    def test_no_installed_kernel_fails_verify(self):
        self.lab.respond("pve1", "ls /boot", stdout="efi\ngrub\n")
        result = self._finish()
        self.assertEqual(result.returncode, 1)
        self.assertIn("verify: no installed kernel found in /boot of pve1: FAILED", result.stdout)


    def test_proxmox_ve_removal_is_seen_even_among_thousands_of_lines(self):
        sim = (fx.APT_SIM.replace("0 to remove", "3001 to remove") + "Remv proxmox-ve [8.4.0]\n"
               + "".join(f"Remv libfoo{n} [1]\n" for n in range(3000)))
        self.lab.respond("pve1", "apt-get -s dist-upgrade", stdout=sim)
        for flag in ("--dry-run", "--yes"):
            result = self.lab.run("pve-update-host", "pve1", flag)
            self.assertEqual(result.returncode, 1, flag)
            self.assertIn("would remove part of the Proxmox stack", result.stdout)
        self.assertEqual(self.lab.commands("admin"), [])

    def test_summary_count_must_match_the_listed_removals(self):
        sim = fx.APT_SIM.replace("0 to remove", "2 to remove") + "Remv libfoo [1.0]\n"
        self.lab.respond("pve1", "apt-get -s dist-upgrade", stdout=sim)
        result = self.lab.run("pve-update-host", "pve1", "--yes")
        self.assertEqual(result.returncode, 1)
        self.assertIn("states 2 package(s) to remove but lists 1", result.stdout)
        self.assertEqual(self.lab.commands("admin"), [])

    def test_removal_that_appears_after_the_update_stops_before_dist_upgrade(self):
        bad = fx.APT_SIM.replace("0 to remove", "1 to remove") + "Remv pve-manager [8.4.1]\n"
        self.lab.respond("pve1", UPDATE)
        self.lab.respond("pve1", UPGRADE)
        self.lab.respond_seq("pve1", "apt-get -s dist-upgrade", {"stdout": fx.APT_SIM_NONE}, {"stdout": bad})
        result = self.lab.run("pve-update-host", "pve1", "--yes")
        self.assertEqual(result.returncode, 1)
        self.assertIn("the post-update simulation on pve1 would remove part of the Proxmox stack (pve-manager)",
                      result.stdout)
        self.assertEqual(self.lab.commands("admin"), [UPDATE])

    def test_unreadable_post_update_simulation_stops_before_dist_upgrade(self):
        self.lab.respond("pve1", UPDATE)
        self.lab.respond_seq("pve1", "apt-get -s dist-upgrade", {"stdout": fx.APT_SIM_NONE},
                             {"stdout": "", "exit": 255, "stderr": "boom\n"})
        result = self.lab.run("pve-update-host", "pve1", "--yes")
        self.assertEqual(result.returncode, 1)
        self.assertIn("post-update simulation failed on pve1: FAILED", result.stdout)
        self.assertEqual(self.lab.commands("admin"), [UPDATE])

    def test_update_failure_stops_before_the_re_simulation(self):
        self.lab.respond("pve1", UPDATE, exit=100, stderr="E: boom\n")
        result = self.lab.run("pve-update-host", "pve1", "--yes")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.lab.commands("admin"), [UPDATE])
        self.assertEqual(self.lab.commands("collect").count("apt-get -s dist-upgrade"), 1)

    def test_two_phases_keep_the_step_numbers(self):
        self.lab.respond("pve1", UPDATE)
        self.lab.respond("pve1", UPGRADE)
        self.lab.respond("pve1", "apt-get -s dist-upgrade", stdout=fx.APT_SIM_NONE)
        result = self.lab.run("pve-update-host", "pve1", "--yes")
        self.assertIn(f"step 1/2: ssh pve1-admin -- {UPDATE}\nresult: exit 0\n", result.stdout)
        self.assertIn("check: the post-update simulation removes no package: ok\nstep 2/2: ssh pve1-admin -- env", result.stdout)

    def test_the_shared_guard_protects_the_stack_and_the_running_kernel(self):
        for name, text in (("qemu-server", "would remove part of the Proxmox stack (qemu-server)"),
                           ("pve-container", "would remove part of the Proxmox stack (pve-container)"),
                           ("proxmox-kernel-6.8.12-10-pve-signed", "would remove the running kernel 6.8.12-10-pve")):
            with self.subTest(name=name):
                sim = fx.APT_SIM.replace("0 to remove", "1 to remove") + f"Remv {name} [1]\n"
                self.lab.respond("pve1", "apt-get -s dist-upgrade", stdout=sim)
                result = self.lab.run("pve-update-host", "pve1", "--yes")
                self.assertEqual(result.returncode, 1)
                self.assertIn(text, result.stdout)
                self.assertEqual(self.lab.commands("admin"), [])

    def test_a_removal_list_that_changes_after_the_update_stops_a_yes_run(self):
        changed = fx.APT_SIM.replace("0 to remove", "1 to remove") + "Remv libbar [1.0]\n"
        self.lab.respond("pve1", UPDATE)
        self.lab.respond("pve1", UPGRADE)
        self.lab.respond_seq("pve1", "apt-get -s dist-upgrade", {"stdout": fx.APT_SIM}, {"stdout": changed})
        result = self.lab.run("pve-update-host", "pve1", "--yes")
        self.assertEqual(result.returncode, 1)
        self.assertIn("removals after apt-get update: libbar (before: none)\n", result.stdout)
        self.assertIn("the removal list changed after apt-get update: review it, then run the tool again: FAILED",
                      result.stdout)
        self.assertEqual(self.lab.commands("admin"), [UPDATE])

    def test_a_changed_removal_list_is_shown_before_the_second_prompt(self):
        changed = fx.APT_SIM.replace("0 to remove", "1 to remove") + "Remv libbar [1.0]\n"
        self.lab.respond("pve1", UPDATE)
        self.lab.respond("pve1", UPGRADE)
        self.lab.respond_seq("pve1", "apt-get -s dist-upgrade", {"stdout": fx.APT_SIM}, {"stdout": changed},
                             {"stdout": fx.APT_SIM_NONE})
        result = self.lab.run_tty(["bash", str(self.lab.root / "bin" / "pve-update-host"), "pve1"], "y\ny\n")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("removals after apt-get update: libbar (before: none)\n", result.stdout)
        self.assertIn("1 to remove", result.stderr)
        self.assertEqual(self.lab.commands("admin"), [UPDATE, UPGRADE])

    def test_declining_phase_two_says_what_ran(self):
        self.lab.respond("pve1", UPDATE)
        self.lab.respond("pve1", "apt-get -s dist-upgrade", stdout=fx.APT_SIM)
        result = self.lab.run_tty(["bash", str(self.lab.root / "bin" / "pve-update-host"), "pve1"], "y\nn\n")
        self.assertEqual(result.returncode, 1)
        self.assertIn("cancelled: apt-get update ran; dist-upgrade was not run\n", result.stdout)
        self.assertEqual(self.lab.commands("admin"), [UPDATE])

    def test_prompt_of_phase_two_carries_the_counts(self):
        self.lab.respond("pve1", UPDATE)
        self.lab.respond("pve1", UPGRADE)
        self.lab.respond("pve1", "apt-get -s dist-upgrade", stdout=fx.APT_SIM)
        result = self.lab.run_tty(["bash", str(self.lab.root / "bin" / "pve-update-host"), "pve1"], "y\ny\n")
        self.assertIn("2 packages to upgrade or install, 0 to remove", result.stdout + result.stderr)

CT_UPDATE = "pct exec 101 -- env DEBIAN_FRONTEND=noninteractive apt-get update"
CT_UPGRADE = ("pct exec 101 -- env DEBIAN_FRONTEND=noninteractive apt-get -y -o Dpkg::Options::=--force-confdef "
              "-o Dpkg::Options::=--force-confold dist-upgrade")
CT_SIM = "pct exec 101 -- env LC_ALL=C apt-get -s dist-upgrade"
APK_SIM_CMD = "pct exec 101 -- apk upgrade --simulate"
APK_SIM = "(1/2) Upgrading musl (1.2.4-r2 -> 1.2.4-r3)\n(2/2) Installing zlib (1.3-r0)\nOK: 9 MiB in 20 packages\n"
APK_NONE = "OK: 9 MiB in 20 packages\n"
ALPINE = lambda: fx.CONFIGS["101"].replace("ostype: debian", "ostype: alpine")


STAMP = lambda: __import__("datetime").datetime.now().strftime("pre-update-%Y%m%d-%H%M")
SNAP_RE = r"re:pct snapshot 101 pre-update-\d{8}-\d{4}"


class UpdateCtTest(unittest.TestCase):
    def setUp(self):
        self._new_lab()

    def _new_lab(self):
        self.lab = Lab()
        self.addCleanup(self.lab.close)
        fx.load(self.lab)

    def same_minute(self, attempt):
        """attempt() on a fresh Lab (own sequence state and call log) until the minute-resolution stamp did
        not change during it, since the tool stamps by the minute. Fails loudly after 3 crossings."""
        for _ in range(3):
            self._new_lab()
            before = STAMP()
            result = attempt()
            if STAMP() == before:
                return result
        self.fail("minute boundary crossed 3 times")

    def test_same_minute_reruns_on_a_fresh_lab(self):
        stamps = iter(["pre-update-20260101-0000", "pre-update-20260101-0001"] + ["pre-update-20260101-0001"] * 10)
        labs = []

        def attempt():
            labs.append(self.lab)
            return self.lab.run("pve-update-ct", "101", "--snapshot", "--dry-run")
        with mock.patch(f"{__name__}.STAMP", lambda: next(stamps)):
            result = self.same_minute(attempt)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(labs), 2)
        self.assertIsNot(labs[0], labs[1])

    def test_same_minute_fails_loudly_when_the_minute_keeps_changing(self):
        counter = iter(range(100))
        with mock.patch(f"{__name__}.STAMP", lambda: f"s{next(counter)}"):
            with self.assertRaisesRegex(self.failureException, "crossed 3 times"):
                self.same_minute(lambda: None)

    def test_dry_run_with_snapshot(self):
        result = self.lab.run("pve-update-ct", "101", "--snapshot", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("check: ct 101 on pve1 uses apt (debian): ok\ncheck: ct 101 is running: ok\n", result.stdout)
        self.assertRegex(result.stdout, r"rollback: pct rollback 101 pre-update-\d{8}-\d{4}\n")
        self.assertRegex(result.stdout, r"step 1/3: ssh pve1-admin -- pct snapshot 101 pre-update-\d{8}-\d{4}\n")
        self.assertIn(f"step 2/3: ssh pve1-admin -- {CT_UPDATE}\n", result.stdout)
        self.assertEqual(self.lab.commands("admin"), [])

    def test_simulate_uses_admin_without_yes(self):
        self.lab.respond("pve1", CT_SIM, stdout=fx.APT_SIM)
        result = self.lab.run("pve-update-ct", "101", "--simulate")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("simulation: 2 packages would be upgraded or installed\n"
                      "note: apt-get update was not run: the simulation reads the package lists as last refreshed; the upgrade refreshes them first\n", result.stdout)
        self.assertEqual(self.lab.commands("admin"), [CT_SIM])

    def test_refuses_vms_stopped_and_unknown_systems(self):
        vm = self.lab.run("pve-update-ct", "200", "--dry-run")
        self.assertEqual(vm.returncode, 1)
        self.assertIn("200 is a VM: pve-update-ct updates containers only", vm.stdout)
        self.lab.respond("pve1", "pct status 101", stdout="status: stopped\n")
        stopped = self.lab.run("pve-update-ct", "101", "--dry-run")
        self.assertIn("ct 101 is stopped: start it first", stopped.stdout)
        self.lab.respond("pve1", "pct config 101", stdout=fx.CONFIGS["101"].replace("ostype: debian", "ostype: nixos"))
        nix = self.lab.run("pve-update-ct", "101", "--dry-run")
        self.assertIn("unsupported ostype 'nixos'", nix.stdout)

    def test_alpine_uses_apk(self):
        self.lab.respond("pve1", "pct config 101", stdout=fx.CONFIGS["101"].replace("ostype: debian", "ostype: alpine"))
        result = self.lab.run("pve-update-ct", "101", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("step 1/2: ssh pve1-admin -- pct exec 101 -- apk update\n"
                      "step 2/2: ssh pve1-admin -- pct exec 101 -- apk upgrade\n", result.stdout)

    def test_yes_updates_and_verifies(self):
        self.lab.respond("pve1", CT_UPDATE)
        self.lab.respond("pve1", CT_UPGRADE)
        self.lab.respond("pve1", CT_SIM, stdout=fx.APT_SIM_NONE)
        result = self.lab.run("pve-update-ct", "101", "--yes")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.endswith("verify: ct 101 is running: ok\nverify: no package left to upgrade: ok\n"))

    def test_a_node_lost_mid_plan_stops_the_tool(self):
        self.lab.respond("pve1", SNAP_RE)
        self.lab.respond("pve1", CT_UPDATE, exit=255, stderr="ssh: connect to host pve1-admin port 22: Broken pipe\n")
        result = self.lab.run("pve-update-ct", "101", "--snapshot", "--yes")
        self.assertEqual(result.returncode, 1)
        self.assertIn("result: exit 255\n", result.stdout)
        self.assertIn("step 2 failed; the remaining steps were not run", result.stderr)
        admin = self.lab.commands("admin")
        self.assertEqual(len(admin), 2)
        self.assertRegex(admin[0], r"^pct snapshot 101 pre-update-\d{8}-\d{4}$")
        self.assertEqual(admin[1], CT_UPDATE)

    def test_leftover_option_and_no_terminal(self):
        self.assertEqual(self.lab.run("pve-update-ct", "101", "--dryrun").returncode, 2)
        result = self.lab.run("pve-update-ct", "101")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.lab.commands("admin"), [])

    def test_unreadable_snapshot_list_fails_the_check(self):
        self.lab.respond("pve1", "pct listsnapshot 101", exit=255, stderr="ssh: boom\n")
        result = self.lab.run("pve-update-ct", "101", "--snapshot", "--dry-run")
        self.assertEqual(result.returncode, 1)
        self.assertIn("cannot read the snapshots of ct 101: FAILED", result.stdout)

    def test_empty_ct_simulation_fails(self):
        self.lab.respond("pve1", CT_SIM, stdout="")
        result = self.lab.run("pve-update-ct", "101", "--simulate")
        self.assertEqual(result.returncode, 1)
        self.assertIn("returned no summary line: FAILED", result.stdout)

    def test_alpine_simulate_is_read_only_and_exact(self):
        self.lab.respond("pve1", "pct config 101", stdout=ALPINE())
        self.lab.respond("pve1", APK_SIM_CMD, stdout=APK_SIM)
        result = self.lab.run("pve-update-ct", "101", "--simulate")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("simulation: 2 packages would be upgraded or installed\n", result.stdout)
        self.assertEqual(self.lab.commands("admin"), [APK_SIM_CMD])

    def test_alpine_yes_runs_and_verifies(self):
        self.lab.respond("pve1", "pct config 101", stdout=ALPINE())
        self.lab.respond("pve1", "pct exec 101 -- apk update")
        self.lab.respond("pve1", "pct exec 101 -- apk upgrade")
        self.lab.respond("pve1", APK_SIM_CMD, stdout=APK_NONE)
        result = self.lab.run("pve-update-ct", "101", "--yes")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.lab.commands("admin"), ["pct exec 101 -- apk update", "pct exec 101 -- apk upgrade", APK_SIM_CMD])
        self.assertTrue(result.stdout.endswith("verify: no package left to upgrade: ok\n"))

    def test_alpine_garbage_simulation_fails(self):
        self.lab.respond("pve1", "pct config 101", stdout=ALPINE())
        self.lab.respond("pve1", APK_SIM_CMD, stdout="garbage\n")
        result = self.lab.run("pve-update-ct", "101", "--simulate")
        self.assertEqual(result.returncode, 1)
        self.assertIn("returned no summary line: FAILED", result.stdout)

    def test_garbage_simulation_fails_verify(self):
        self.lab.respond("pve1", CT_UPDATE)
        self.lab.respond("pve1", CT_UPGRADE)
        self.lab.respond("pve1", CT_SIM, stdout="garbage\n")
        result = self.lab.run("pve-update-ct", "101", "--yes")
        self.assertEqual(result.returncode, 1)
        self.assertIn("verify: the simulation after the upgrade returned no summary line: FAILED", result.stdout)
        self.assertNotIn("no package left to upgrade: ok", result.stdout)

    def test_simulate_conflicts_are_usage_errors(self):
        for flag in ("--dry-run", "--snapshot"):
            result = self.lab.run("pve-update-ct", "101", "--simulate", flag)
            self.assertEqual(result.returncode, 2, flag)
        self.assertEqual(self.lab.calls(), [])

    def test_empty_config_and_status_fail_the_check(self):
        self.lab.respond("pve1", "pct config 101", stdout="")
        result = self.lab.run("pve-update-ct", "101", "--dry-run")
        self.assertEqual(result.returncode, 1)
        self.assertIn("cannot read the config of ct 101: empty answer: FAILED", result.stdout)
        lab = Lab()
        self.addCleanup(lab.close)
        fx.load(lab)
        lab.respond("pve1", "pct status 101", stdout="")
        result = lab.run("pve-update-ct", "101", "--dry-run")
        self.assertEqual(result.returncode, 1)
        self.assertIn("cannot read the status of ct 101: empty answer: FAILED", result.stdout)

    def test_stopped_after_the_upgrade_fails_verify(self):
        self.lab.respond("pve1", CT_UPDATE)
        self.lab.respond("pve1", CT_UPGRADE)
        self.lab.respond("pve1", CT_SIM, stdout=fx.APT_SIM_NONE)
        self.lab.respond_seq("pve1", "pct status 101", {"stdout": "status: running\n"}, {"stdout": "status: stopped\n"})
        result = self.lab.run("pve-update-ct", "101", "--yes")
        self.assertEqual(result.returncode, 1)
        self.assertIn("verify: ct 101 is stopped after the upgrade: FAILED", result.stdout)

    def test_snapshot_name_already_used_fails(self):
        def attempt():
            listed = fx.SNAPSHOTS["101"].replace(" `-> current", f" `-> {STAMP()}  2026-07-01 10:00:00  x\n    `-> current")
            self.lab.respond("pve1", "pct listsnapshot 101", stdout=listed)
            return self.lab.run("pve-update-ct", "101", "--snapshot", "--dry-run")
        result = self.same_minute(attempt)
        self.assertEqual(result.returncode, 1)
        self.assertIn("already has a snapshot named pre-update-", result.stdout)
        self.assertEqual(self.lab.commands("admin"), [])

    def test_snapshot_needs_a_capable_storage(self):
        self.lab.respond("pve1", "pct config 101",
                         stdout=fx.CONFIGS["101"].replace("local-lvm:vm-101-disk-0", "local:101/vm-101-disk-0.raw"))
        result = self.lab.run("pve-update-ct", "101", "--snapshot", "--dry-run")
        self.assertEqual(result.returncode, 1)
        self.assertIn("which cannot snapshot it", result.stdout)

    def _snapshot_run(self, second):
        self.lab.respond("pve1", SNAP_RE)
        self.lab.respond("pve1", CT_UPDATE)
        self.lab.respond("pve1", CT_UPGRADE)
        self.lab.respond("pve1", CT_SIM, stdout=fx.APT_SIM_NONE)
        self.lab.respond_seq("pve1", "pct listsnapshot 101", {"stdout": fx.SNAPSHOTS["101"]}, second)
        return self.lab.run("pve-update-ct", "101", "--snapshot", "--yes")

    def test_snapshot_is_verified_after_the_plan(self):
        def attempt():
            listed = fx.SNAPSHOTS["101"].replace(" `-> current", f" `-> {STAMP()}  2026-07-01 10:00:00  x\n    `-> current")
            return self._snapshot_run({"stdout": listed})
        result = self.same_minute(attempt)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertRegex(result.stdout, r"verify: snapshot pre-update-\d{8}-\d{4} is listed: ok\n")

    def test_missing_or_unreadable_snapshot_fails_verify(self):
        missing = self._snapshot_run({"stdout": fx.SNAPSHOTS["101"]})
        self.assertEqual(missing.returncode, 1)
        self.assertIn("is not listed after the command: FAILED", missing.stdout)
        self.lab = Lab()
        self.addCleanup(self.lab.close)
        fx.load(self.lab)
        unreadable = self._snapshot_run({"stdout": "", "exit": 255, "stderr": "boom\n"})
        self.assertEqual(unreadable.returncode, 1)
        self.assertIn("cannot read the snapshots of ct 101 after the command: FAILED", unreadable.stdout)


if __name__ == "__main__":
    unittest.main()
