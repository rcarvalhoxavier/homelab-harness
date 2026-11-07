import hashlib
import shutil
import subprocess
import unittest
import uuid

from tests import pvefixtures as fx
from tests.toolkit import Lab

LOAD = "pve_env_load\npve_inventory_load\n"


class QueryTest(unittest.TestCase):
    def setUp(self):
        self.lab = Lab()
        self.addCleanup(self.lab.close)
        fx.load(self.lab)

    def test_guests_of_a_node(self):
        result = self.lab.bash(LOAD + "pve_guests pve2")
        self.assertEqual(result.stdout, "102 ct running pihole\n200 vm running nas\n")

    def test_find_guest(self):
        result = self.lab.bash(LOAD + 'pve_find_guest 200; echo "$PVE_GUEST_NODE $PVE_GUEST_TYPE"')
        self.assertEqual(result.stdout, "pve2 vm\n")
        missing = self.lab.bash(LOAD + "pve_find_guest 999")
        self.assertEqual(missing.returncode, 1)
        self.assertIn("guest 999 not found on any node", missing.stderr)
        self.lab.unreachable("pve2")
        partial = self.lab.bash(LOAD + "pve_find_guest 200")
        self.assertIn("could not read: pve2", partial.stderr)

    def duplicate_101(self):
        """Two nodes that are not in one cluster: pve2 also has a CT 101."""
        self.lab.respond("pve2", "pct list", stdout=fx.pct_list([("101", "running", "pihole"),
                                                                 ("102", "running", "pihole")]))
        for command in ("pct status 101", "pct config 101", "pct listsnapshot 101"):
            self.lab.respond("pve2", command, **self.lab.responses["pve1"][command])

    def test_find_guest_refuses_a_vmid_on_two_nodes(self):
        self.duplicate_101()
        result = self.lab.bash(LOAD + 'pve_find_guest 101; echo "found $PVE_GUEST_NODE"')
        self.assertEqual(result.returncode, 2)
        self.assertIn("VMID 101 is on pve1 and pve2; pass --node NODE", result.stderr)
        self.assertNotIn("found", result.stdout)

    def test_node_option_picks_the_node(self):
        self.duplicate_101()
        result = self.lab.bash('usage() { echo usage; }\npve_cli_parse --node pve2 101\npve_init demo\n'
                               'pve_find_guest 101; echo "$PVE_GUEST_NODE ${PVE_ARGS[*]}"')
        self.assertEqual(result.stdout, "pve2 101\n", result.stderr)
        self.assertEqual({call["node"] for call in self.lab.calls()}, {"pve2"})
        absent = self.lab.bash('usage() { echo usage; }\npve_cli_parse --node pve2\npve_init demo\npve_find_guest 200; '
                               'pve_find_guest 999')
        self.assertEqual(absent.returncode, 1)
        self.assertIn("guest 999 not found on pve2", absent.stderr)

    def test_node_option_is_validated(self):
        for args, message in (("--node", "--node needs a value"), ("--node pve9", "unknown node 'pve9'")):
            with self.subTest(args=args):
                result = self.lab.bash(f'usage() {{ echo usage; }}\npve_cli_parse {args}\npve_init demo\necho ran')
                self.assertEqual(result.returncode, 2)
                self.assertIn(message, result.stderr)
                self.assertNotIn("ran", result.stdout)

    def test_find_guest_reports_why_a_node_could_not_be_read(self):
        self.lab.unreachable("pve1")
        found = self.lab.bash(LOAD + 'pve_find_guest 200; echo "$PVE_GUEST_NODE"')
        self.assertEqual((found.returncode, found.stdout), (0, "pve2\n"), found.stderr)
        missing = self.lab.bash(LOAD + "pve_find_guest 999")
        self.assertEqual(missing.returncode, 1)
        self.assertIn("could not read: pve1", missing.stderr)
        self.assertIn("ssh: connect to host pve1 port 22: No route to host", missing.stderr)

    def standalone(self, node: str):
        self.lab.respond(node, "cat /etc/pve/corosync.conf", exit=1)
        self.lab.respond(node, "ls /etc/pve/nodes", stdout=f"{node}\n")

    def test_find_guest_trusts_a_member_of_its_cluster_that_is_down(self):
        # a cluster keeps VMIDs unique, so pve1 (down) cannot list 200 as well
        self.lab.unreachable("pve1")
        found = self.lab.bash(LOAD + 'pve_find_guest 200; echo "$PVE_GUEST_NODE"')
        self.assertEqual((found.returncode, found.stdout), (0, "pve2\n"), found.stderr)

    def test_find_guest_stops_when_an_unreadable_node_is_outside_its_cluster(self):
        self.standalone("pve2")
        self.lab.unreachable("pve1")
        result = self.lab.bash(LOAD + 'pve_find_guest 200; echo "found $PVE_GUEST_NODE"')
        self.assertEqual(result.returncode, 2)
        self.assertIn("VMID 200 is on pve2, but pve1 could not be read and may list it too; "
                      "pass --node NODE", result.stderr)
        self.assertNotIn("found", result.stdout)

    def test_find_guest_stops_when_the_cluster_members_cannot_be_read(self):
        self.lab.respond("pve2", "pvecm nodes", exit=255, stderr="ssh: lost\n")
        self.lab.unreachable("pve1")
        result = self.lab.bash(LOAD + 'pve_find_guest 200; echo "found $PVE_GUEST_NODE"')
        self.assertEqual(result.returncode, 2)
        self.assertIn("pass --node NODE", result.stderr)

    def test_find_guest_keeps_the_quorum_globals_of_the_caller(self):
        self.lab.unreachable("pve1")
        result = self.lab.bash(LOAD + 'PVE_QUORUM_STATE=mine\npve_find_guest 200; echo "$PVE_QUORUM_STATE"')
        self.assertEqual(result.stdout, "mine\n", result.stderr)

    def test_find_guest_keeps_a_configuration_error_at_exit_2(self):
        lab = Lab()
        self.addCleanup(lab.close)
        fx.load(lab)
        lab.write_env("HOMELAB_SSHPASS=1\nSSHPASS=x\n")
        tools = lab.base / "tools"
        tools.mkdir()
        for name in ("bash", "mktemp", "grep", "cat", "rm", "dirname", "sed", "awk", "date", "uname",
                     "env", "tr", "sort", "id", "hostname", "mkdir", "tee", "cut", "head", "wc", "basename"):
            found = shutil.which(name)
            if found:
                (tools / name).symlink_to(found)
        result = lab.bash(LOAD + "pve_find_guest 200", PATH=str(tools))
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("needs sshpass", result.stderr)

    def test_apt_comment_does_not_count_as_a_match(self):
        lab = self.lab
        line = ("deb http://download.proxmox.com/debian/pve bookworm pve-no-subscription "
                "# replaces enterprise.proxmox.com\n")
        (lab.base / "c.list").write_text(line)
        result = lab.bash(f'd="{lab.base}/d"; mkdir "$d"; cp {lab.base}/c.list "$d/1"\n'
                          "printf '1 /etc/apt/sources.list.d/c.list\\n' > \"$d/index\"\n"
                          "pve_apt_enabled \"$d\" 'enterprise\\.proxmox\\.com' '.'\necho --\n"
                          "pve_apt_enabled \"$d\" 'download\\.proxmox\\.com' 'pve-no-subscription'\necho --\n"
                          f"pve_apt_disable {lab.base}/c.list /etc/apt/sources.list.d/c.list "
                          "'enterprise\\.proxmox\\.com'")
        self.assertEqual(result.stdout, "--\n/etc/apt/sources.list.d/c.list\n--\n" + line, result.stderr)

    def test_snapshot_lookup_unreadable_is_2(self):
        self.lab.respond("pve1", "pct listsnapshot 101", exit=255, stderr="ssh: boom\n")
        failed = self.lab.bash(LOAD + "rc=0; pve_guest_has_snapshot pve1 ct 101 x1 || rc=$?; echo rc$rc")
        self.assertEqual(failed.stdout, "rc2\n")
        self.assertIn("boom", failed.stderr)
        self.lab.respond("pve1", "pct listsnapshot 101", stdout="")
        empty = self.lab.bash(LOAD + "rc=0; pve_guest_has_snapshot pve1 ct 101 x1 || rc=$?; echo rc$rc")
        self.assertEqual(empty.stdout, "rc2\n")

    def test_capability_fails_on_empty_config(self):
        self.lab.respond("pve1", "pct config 101", stdout="")
        result = self.lab.bash(LOAD + "pve_require_snapshot_capable pve1 ct 101")
        self.assertEqual(result.returncode, 1)
        self.assertIn("check: cannot read the config of ct 101: empty answer: FAILED", result.stdout)

    def test_capability_fails_on_a_passthrough_disk(self):
        config = fx.CONFIGS["200"] + "scsi1: /dev/disk/by-id/ata-EXAMPLE_SERIAL,iothread=1,size=1863G\n"
        self.lab.respond("pve2", "qm config 200", stdout=config)
        result = self.lab.bash(LOAD + "pve_require_snapshot_capable pve2 vm 200")
        self.assertEqual(result.returncode, 1)
        self.assertIn("check: scsi1 of vm 200 is a passthrough device (/dev/disk/by-id/ata-EXAMPLE_SERIAL), "
                      "which cannot be snapshotted: FAILED", result.stdout)

    def test_capability_ignores_a_bind_mount(self):
        self.lab.respond("pve1", "pct config 101", stdout=fx.CONFIGS["101"] + "mp0: /mnt/data,mp=/data\n")
        result = self.lab.bash(LOAD + "pve_require_snapshot_capable pve1 ct 101")
        self.assertEqual(result.stdout, "check: every disk of ct 101 supports snapshots: ok\n")

    def test_capability_ignores_cdrom_and_none_values(self):
        config = fx.CONFIGS["200"] + "ide0: none,media=cdrom\nsata0: /dev/sr0,media=cdrom\n"
        self.lab.respond("pve2", "qm config 200", stdout=config)
        result = self.lab.bash(LOAD + "pve_require_snapshot_capable pve2 vm 200")
        self.assertEqual(result.stdout, "check: every disk of vm 200 supports snapshots: ok\n")

    def test_snapshots_and_capability(self):
        result = self.lab.bash(LOAD + "pve_guest_has_snapshot pve1 ct 101 pre-upgrade && echo yes\n"
                                      "pve_guest_has_snapshot pve1 ct 101 nope || echo no$?\n"
                                      "pve_require_snapshot_capable pve1 ct 101")
        self.assertEqual(result.stdout, "yes\nno1\ncheck: every disk of ct 101 supports snapshots: ok\n")
        for storage_type, volume, expected in (("lvmthin", "vm-1-disk-0", 0), ("zfspool", "x", 0),
                                               ("dir", "100/vm-100-disk-0.qcow2", 0),
                                               ("dir", "100/vm-100-disk-0.raw", 1), ("lvm", "x", 1)):
            with self.subTest(storage_type=storage_type, volume=volume):
                check = self.lab.bash(f"pve_snapshot_capable {storage_type} {volume}")
                self.assertEqual(check.returncode, expected)

    def test_storage_queries(self):
        result = self.lab.bash(LOAD + "pve_storage_line pve1 nas-backup\npve_storage_content pve1 nas-backup\n"
                                      "pve_guest_backups pve1 nas-backup 101")
        self.assertEqual(result.stdout,
                         "nas-backup nfs active 1951350784 512340224 1439010560 26.26\nbackup\n"
                         "2026-06-29T23:00:03 nas-backup:backup/vzdump-lxc-101-2026_06_29-23_00_03.tar.zst\n"
                         "2026-06-30T23:00:02 nas-backup:backup/vzdump-lxc-101-2026_06_30-23_00_02.tar.zst\n")

    def test_apt_sources_on_both_versions(self):
        for version, enterprise in (("8", ["/etc/apt/sources.list.d/ceph.list",
                                           "/etc/apt/sources.list.d/pve-enterprise.list"]),
                                    ("9", ["/etc/apt/sources.list.d/ceph.sources",
                                           "/etc/apt/sources.list.d/pve-enterprise.sources"])):
            with self.subTest(version=version):
                lab = Lab()
                self.addCleanup(lab.close)
                fx.load(lab, version)
                result = lab.bash(LOAD + 'd="$(mktemp -d)"; pve_apt_fetch pve1 "$d"\n'
                                         "pve_apt_enabled \"$d\" 'enterprise\\.proxmox\\.com' '.'\n"
                                         "echo --\n"
                                         "pve_apt_enabled \"$d\" 'download\\.proxmox\\.com/debian/pve' "
                                         "'pve-no-subscription'")
                self.assertEqual(result.stdout, "\n".join(enterprise) + "\n--\n", result.stderr)

    def test_apt_disable(self):
        lab = self.lab
        (lab.base / "a.list").write_text("deb https://enterprise.proxmox.com/debian/pve bookworm pve-enterprise\n"
                                         "deb http://deb.debian.org/debian bookworm main\n")
        (lab.base / "b.sources").write_text(fx.SOURCES["9"]["/etc/apt/sources.list.d/debian.sources"] + "\n" +
                                            "Types: deb\nURIs: https://enterprise.proxmox.com/debian/pve\n"
                                            "Suites: trixie\nEnabled: yes\nComponents: pve-enterprise\n")
        result = lab.bash(f"pve_apt_disable {lab.base}/a.list /etc/apt/sources.list.d/a.list 'enterprise\\.proxmox\\.com'\n"
                          f"echo --\npve_apt_disable {lab.base}/b.sources /etc/apt/sources.list.d/b.sources "
                          "'enterprise\\.proxmox\\.com'")
        listed, deb822 = result.stdout.split("--\n")
        self.assertEqual(listed, "# deb https://enterprise.proxmox.com/debian/pve bookworm pve-enterprise\n"
                                 "deb http://deb.debian.org/debian bookworm main\n")
        self.assertIn("URIs: https://enterprise.proxmox.com/debian/pve\nSuites: trixie\nEnabled: no\n", deb822)
        self.assertEqual(deb822.count("Enabled: no"), 1)
        self.assertIn("URIs: http://deb.debian.org/debian/\n", deb822)

    def test_collect_hash_matches_python(self):
        self.lab.write_local("collect.allow", "pct exec 101 -- pihole -v\n")
        result = self.lab.bash("pve_collect_hash")
        self.assertEqual(result.stdout.strip(), fx.collect_hash(self.lab.root))
        data = b"".join((self.lab.root / p).read_bytes()
                        for p in ("remote/homelab-collect", "remote/collect.allow", "local/collect.allow"))
        self.assertEqual(result.stdout.strip(), hashlib.sha256(data).hexdigest()[:16])


DEMO = """\
usage() { echo "Usage: demo"; }
pve_cli_parse "$@"
pve_env_load
pve_inventory_load
pve_plan_reset
pve_hint target "ct 101 on pve1"
pve_hint path trivial
pve_plan_add pve1 pct snapshot 101 a
pve_plan_add pve1 pct snapshot 101 b
pve_plan_execute "Take two snapshots?" || exit 1
echo "outputs: ${#PVE_STEP_OUT[@]}"
"""


class PlanTest(unittest.TestCase):
    def setUp(self):
        self.lab = Lab()
        self.addCleanup(self.lab.close)
        (self.lab.root / "demo").write_text("source lib/pve/init.sh\n" + DEMO)

    def demo(self, *args):
        return self.lab.shell("bash demo " + " ".join(args))

    def test_help(self):
        result = self.demo("--help")
        self.assertEqual((result.returncode, result.stdout), (0, "Usage: demo\n"))

    def test_dry_run_prints_and_changes_nothing(self):
        result = self.demo("--dry-run")
        self.assertEqual(result.stdout,
                         "target: ct 101 on pve1\npath: trivial\n"
                         "step 1/2: ssh pve1-admin -- pct snapshot 101 a\n"
                         "step 2/2: ssh pve1-admin -- pct snapshot 101 b\n"
                         "dry run: nothing was changed\noutputs: 0\n")
        self.assertEqual(self.lab.calls(), [])

    def test_plan_numbering_offsets_and_resets(self):
        result = self.lab.bash(
            'pve_env_load; pve_inventory_load; pve_plan_reset; pve_plan_numbering 1 3; pve_plan_add pve1 pct snapshot 101 a\n'
            '_pve_plan_describe 0; pve_plan_reset; '
            'pve_plan_add pve1 pct snapshot 101 b; _pve_plan_describe 0')
        self.assertEqual(result.stdout, "step 2/3: ssh pve1-admin -- pct snapshot 101 a\n"
                                        "step 1/1: ssh pve1-admin -- pct snapshot 101 b\n")

    def test_no_terminal_and_no_yes_refuses(self):
        result = self.demo()
        self.assertEqual(result.returncode, 2)
        self.assertIn("re-run with --yes", result.stderr)
        self.assertEqual(self.lab.calls(), [])

    def test_yes_runs_every_step_in_order(self):
        self.lab.respond("pve1", "pct snapshot 101 a", stdout="first\n")
        self.lab.respond("pve1", "pct snapshot 101 b")
        result = self.demo("--yes")
        self.assertEqual(result.stdout,
                         "target: ct 101 on pve1\npath: trivial\n"
                         "step 1/2: ssh pve1-admin -- pct snapshot 101 a\nfirst\nresult: exit 0\n"
                         "step 2/2: ssh pve1-admin -- pct snapshot 101 b\nresult: exit 0\noutputs: 2\n")
        self.assertEqual(self.lab.commands("admin"), ["pct snapshot 101 a", "pct snapshot 101 b"])

    def test_a_failed_step_stops_the_plan(self):
        self.lab.respond("pve1", "pct snapshot 101 a", exit=5, stderr="boom\n")
        result = self.demo("--yes")
        self.assertEqual(result.returncode, 1)
        self.assertIn("result: exit 5", result.stdout)
        self.assertIn("step 1 failed; the remaining steps were not run", result.stderr)
        self.assertEqual(self.lab.commands("admin"), ["pct snapshot 101 a"])

    def test_terminal_answer(self):
        self.lab.respond("pve1", "pct snapshot 101 a")
        self.lab.respond("pve1", "pct snapshot 101 b")
        no = self.lab.run_tty(["bash", "demo"], "n\n")
        self.assertEqual(no.returncode, 1)
        self.assertIn("cancelled", no.stdout)
        self.assertIn("Take two snapshots? [y/N]", no.stderr)
        self.assertEqual(self.lab.calls(), [])
        yes = self.lab.run_tty(["bash", "demo"], "y\n")
        self.assertEqual(yes.returncode, 0, yes.stderr)

    def test_put_steps_show_their_content_in_a_dry_run(self):
        script = ('pve_cli_parse --dry-run\npve_env_load\npve_inventory_load\npve_plan_reset\n'
                  'f="$(mktemp)"; printf "line one\\n" > "$f"\n'
                  'pve_plan_put pve1 "$f" /etc/demo.conf 0644\npve_plan_execute "Write?"')
        result = self.lab.bash(script)
        self.assertEqual(result.stdout, "step 1/1: put /etc/demo.conf (mode 0644) on pve1-admin\n"
                                        "    | line one\ndry run: nothing was changed\n")

    def test_a_put_step_can_show_a_summary_instead_of_its_content(self):
        script = ('pve_cli_parse --dry-run\npve_env_load\npve_inventory_load\npve_plan_reset\n'
                  'f="$(mktemp)"; printf "line one\\nline two\\n" > "$f"\n'
                  'pve_plan_put pve1 "$f" /etc/demo.conf 0644 summary\npve_plan_execute "Write?"')
        result = self.lab.bash(script)
        digest = hashlib.sha256(b"line one\nline two\n").hexdigest()[:16]
        self.assertEqual(result.stdout, "step 1/1: put /etc/demo.conf (mode 0644) on pve1-admin\n"
                                        f"    (2 lines, sha256 {digest}; content not shown)\n"
                                        "dry run: nothing was changed\n")

    def test_checks_and_usage_errors(self):
        result = self.lab.bash("usage() { echo use; }\npve_check_ok fine\npve_check_warn careful\n"
                               "pve_check_fail broken\necho unreachable")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "check: fine: ok\ncheck: careful: WARNING\ncheck: broken: FAILED\n")
        usage = self.lab.bash("usage() { echo use; }\npve_usage_error 'bad thing'")
        self.assertEqual(usage.returncode, 2)
        self.assertIn("bad thing", usage.stderr)
        self.assertIn("use", usage.stderr)

    def test_timeout(self):
        result = self.lab.bash('o="$(mktemp)"; rc=0; pve_run_timeout 1 "$o" sleep 5 || rc=$?; echo "$rc"\n'
                               'rc=0; pve_run_timeout 5 "$o" bash -c "echo hi; exit 3" || rc=$?; echo "$rc"; cat "$o"')
        self.assertEqual(result.stdout, "124\n3\nhi\n")

    def test_timeout_kills_a_command_that_ignores_term_and_its_children(self):
        # a duration no other process uses: pgrep must find only this test's survivors
        marker = f"sleep 37.{uuid.uuid4().int % 10**12:012d}"
        result = self.lab.bash(
            'o="$(mktemp)"; start=$SECONDS; rc=0\n'
            f'pve_run_timeout 1 "$o" bash -c \'trap "" TERM; {marker} & wait\' || rc=$?\n'
            'echo "$rc $((SECONDS - start))"; echo "m:$-"')
        lines = result.stdout.split("\n")
        rc, elapsed = map(int, lines[0].split())
        self.assertEqual(rc, 124)
        self.assertLessEqual(elapsed, 6)
        self.assertNotIn("m", lines[1].split(":")[1])
        alive = subprocess.run(["pgrep", "-f", marker], capture_output=True, text=True)
        self.assertEqual(alive.stdout, "")


class NodeOptionTest(unittest.TestCase):
    """--node is common to every tool: it names the node of a VMID target, or the only node a
    collector reads; with a node target it must name that same node."""

    def setUp(self):
        self.lab = Lab()
        self.addCleanup(self.lab.close)
        fx.load(self.lab)

    def test_a_node_target_and_another_node_is_a_usage_error(self):
        for run in (("pve-update-host", "pve1", "--node", "pve2", "--dry-run"),
                    ("pve-cleanup", "pve1", "--node", "pve2", "--dry-run"),
                    ("pve-repo-setup", "pve1", "--node", "pve2", "--dry-run"),
                    ("pve-collect-install", "pve1", "--node", "pve2", "--dry-run"),
                    ("pve-state", "pve1", "--node", "pve2")):
            with self.subTest(run=run):
                result = self.lab.run(*run)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn("--node pve2 does not match the target node pve1", result.stderr)
        self.assertEqual(self.lab.commands("admin"), [])

    def test_the_same_node_is_accepted(self):
        result = self.lab.run("pve-state", "pve1", "--node", "pve1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.startswith("pve-state 1 | node pve1\n"))

    def test_collectors_keep_their_meaning(self):
        for tool in ("pve-health", "pve-capacity", "pve-selftest"):
            with self.subTest(tool=tool):
                self.lab.log.unlink(missing_ok=True)
                result = self.lab.run(tool, "--node", "pve2")
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertNotIn("== node pve1", result.stdout)
                self.assertNotIn("PASS pve1", result.stdout)
                if tool != "pve-capacity":   # capacity reads every node's guest configs (shared storages)
                    self.assertNotIn("pve1", {call["node"] for call in self.lab.calls()})


if __name__ == "__main__":
    unittest.main()
