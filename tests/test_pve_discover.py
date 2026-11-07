import re
import unittest

from tests import pvefixtures as fx
from tests.toolkit import Lab

V = fx.VERSIONS["8"]
VERSION = f"pve-manager/{V['manager']} (running kernel: {V['kernel']})"
CT101 = "  101 ct pve1 running pihole cores=1 memory=512 swap=512 disks=rootfs:8G onboot=1\n"
CT102 = "  102 ct pve2 running pihole cores=1 memory=512 swap=512 disks=rootfs:8G onboot=1\n"
VM200 = "  200 vm pve2 running nas cores=2 memory=4096 disks=scsi0:32G\n"
GUESTS = "guests:\n" + CT101 + CT102 + VM200
STORAGES = ("storages:\n  local dir pve1:active pve2:active\n  local-lvm lvmthin pve1:active pve2:active\n"
            "  nas-backup nfs pve1:active pve2:active\n")
ADMIN = "admin aliases: not tested; inventory/nodes assumes <node>-admin\n"
UNREACHABLE = "unreachable (alias {0}: ssh: connect to host {0} port 22: No route to host)"


def fresh_lab(test, nodes=("pve1", "pve2")) -> Lab:
    """A lab with fixtures but no inventory/nodes: a fresh install."""
    lab = Lab(nodes=nodes)
    test.addCleanup(lab.close)
    fx.load(lab)
    (lab.root / "inventory" / "nodes").unlink()
    return lab


def inventory(lab: Lab) -> str:
    return (lab.root / "inventory" / "nodes").read_text()


class SeedTest(unittest.TestCase):
    def assertInventory(self, lab: Lab, seed: str, body: str):
        header = (rf"# written by pve-discover --seed {re.escape(seed)} on \d{{4}}-\d\d-\d\d; edit freely\n"
                  r"# node collect admin\n")
        self.assertIsNotNone(re.fullmatch(header + re.escape(body), inventory(lab)), inventory(lab))

    def assertNoInventory(self, lab: Lab):
        self.assertFalse((lab.root / "inventory" / "nodes").exists())

    def test_a_seed_on_a_cluster_writes_the_inventory_and_the_report(self):
        lab = fresh_lab(self)
        result = lab.run("pve-discover", "--seed", "pve1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout,
                         "pve-discover 1 | cluster lab\nnodes:\n"
                         f"  pve1 seed reachable {VERSION}\n  pve2 reachable {VERSION}\n"
                         "inventory: written\n" + ADMIN + STORAGES + GUESTS)
        self.assertInventory(lab, "pve1", "pve1\npve2\n")
        self.assertEqual(lab.commands("admin"), [])
        self.assertEqual([call["command"] for call in lab.calls() if call["unexpected"]], [])

    def test_a_seed_alias_that_differs_from_the_node_name_gets_the_collect_column(self):
        lab = fresh_lab(self)
        lab.aliases["lab1"] = {"role": "collect", "node": "pve1", "restricted": True}
        result = lab.run("pve-discover", "--seed", "lab1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"  pve1 seed reachable {VERSION}\n", result.stdout)
        self.assertInventory(lab, "lab1", "pve1 lab1\npve2\n")
        self.assertEqual(sorted({call["alias"] for call in lab.calls()}), ["lab1", "pve2"])

    def test_an_admin_alias_as_seed_is_refused_before_any_ssh_call(self):
        # discovery never reads through the unrestricted key
        lab = fresh_lab(self)
        result = lab.run("pve-discover", "--seed", "pve1-admin")
        self.assertEqual(result.returncode, 2)
        self.assertIn("admin alias", result.stderr)
        self.assertEqual(lab.calls(), [])
        self.assertNoInventory(lab)

    def test_a_standalone_node(self):
        lab = fresh_lab(self, nodes=("pve1",))
        fx.standalone(lab, "pve1")
        result = lab.run("pve-discover", "--seed", "pve1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout,
                         f"pve-discover 1 | standalone\nnodes:\n  pve1 seed reachable {VERSION}\n"
                         "inventory: written\n" + ADMIN +
                         "storages:\n  local dir pve1:active\n  local-lvm lvmthin pve1:active\n"
                         "  nas-backup nfs pve1:active\nguests:\n" + CT101)
        self.assertInventory(lab, "pve1", "pve1\n")

    def test_a_standalone_node_that_lists_several_names(self):
        lab = fresh_lab(self, nodes=("pve1",))
        fx.standalone(lab, "pve1")
        lab.respond("pve1", "ls /etc/pve/nodes", stdout="old\npve1\n")
        result = lab.run("pve-discover", "--seed", "pve1")
        self.assertEqual(result.returncode, 1)
        self.assertIn("pass --name NODE", result.stderr)
        self.assertIn("(old pve1)", result.stderr)
        self.assertNoInventory(lab)
        result = lab.run("pve-discover", "--seed", "pve1", "--name", "pve9")
        self.assertEqual(result.returncode, 2)
        self.assertIn("--name pve9 is not a member", result.stderr)
        self.assertNoInventory(lab)
        result = lab.run("pve-discover", "--seed", "pve1", "--name", "pve1")
        self.assertEqual(result.returncode, 1)
        self.assertIn(f"  old {UNREACHABLE.format('old')}\n", result.stdout)
        self.assertTrue(result.stdout.endswith("guests not read: old\n"), result.stdout)
        self.assertInventory(lab, "pve1", "pve1\n")

    def test_an_unreachable_member_is_left_out(self):
        lab = fresh_lab(self)
        lab.unreachable("pve2")
        result = lab.run("pve-discover", "--seed", "pve1")
        self.assertEqual(result.returncode, 1)
        self.assertIn(f"  pve2 {UNREACHABLE.format('pve2')}\n", result.stdout)
        self.assertIn('inventory: written\n  left out: pve2 (add the line "pve2" once its alias connects)\n' + ADMIN,
                      result.stdout)
        self.assertIn("guests:\n" + CT101 + "guests not read: pve2\n", result.stdout)
        self.assertTrue(result.stdout.endswith("guests not read: pve2\n"))
        self.assertInventory(lab, "pve1", "pve1\n")

    def test_a_member_with_an_invalid_name_is_marked(self):
        lab = fresh_lab(self)
        lab.respond("pve1", "pvecm nodes", stdout=fx.PVECM_NODES.format(local1=" (local)", local2="")
                    + "         3          1 bad_name\n")
        result = lab.run("pve-discover", "--seed", "pve1")
        self.assertEqual(result.returncode, 1)
        self.assertIn("  bad_name invalid name\n", result.stdout)
        self.assertInventory(lab, "pve1", "pve1\npve2\n")

    def test_an_unreachable_seed_writes_nothing(self):
        lab = fresh_lab(self)
        lab.unreachable("pve1")
        result = lab.run("pve-discover", "--seed", "pve1")
        self.assertEqual(result.returncode, 1)
        self.assertIn("docs/ssh-access.md", result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertNoInventory(lab)

    def test_a_member_whose_alias_is_the_seeds_is_not_probed(self):
        lab = fresh_lab(self)
        lab.aliases["pve2"]["node"] = "pve1"     # the alias pve2 reaches pve1
        result = lab.run("pve-discover", "--seed", "pve2")
        self.assertEqual(result.returncode, 1)
        self.assertIn("  pve2 unreachable (alias pve2 is already used by node pve1)\n", result.stdout)
        # adding the line "pve2" would clash with the seed's alias
        self.assertIn('  left out: pve2 (give it a collect alias of its own, then add the line "pve2 <alias>")\n',
                      result.stdout)
        self.assertInventory(lab, "pve2", "pve1 pve2\n")

    def test_seed_with_an_existing_inventory_is_refused(self):
        lab = Lab()
        self.addCleanup(lab.close)
        fx.load(lab)
        result = lab.run("pve-discover", "--seed", "pve1")
        self.assertEqual(result.returncode, 2)
        self.assertIn("run pve-discover without --seed to reconcile", result.stderr)
        self.assertEqual(inventory(lab), "pve1\npve2\n")
        self.assertEqual(lab.calls(), [])

    def test_no_inventory_and_no_seed_is_refused(self):
        lab = fresh_lab(self)
        result = lab.run("pve-discover")
        self.assertEqual(result.returncode, 2)
        self.assertIn("pve-discover --seed ALIAS", result.stderr)

    def test_usage_errors(self):
        lab = fresh_lab(self)
        for args in (("--name", "pve1"), ("--seed",), ("--seed", "pve1", "extra"), ("--dry-run",),
                     ("--yes",), ("--node", "pve1"), ("--seed", "bad/alias")):
            with self.subTest(args=args):
                self.assertEqual(lab.run("pve-discover", *args).returncode, 2)
        result = lab.run("pve-discover", "--help")
        self.assertEqual(result.returncode, 0)
        self.assertTrue(result.stdout.startswith("Usage: pve-discover"))
        self.assertNoInventory(lab)

    def test_the_report_is_byte_identical_across_runs(self):
        lab = fresh_lab(self)
        first = lab.run("pve-discover", "--seed", "pve1").stdout
        (lab.root / "inventory" / "nodes").unlink()
        self.assertEqual(lab.run("pve-discover", "--seed", "pve1").stdout, first)

    def test_a_dispatcher_refusal_is_a_failed_read_with_a_hint(self):
        lab = fresh_lab(self)
        lab.respond("pve1", "pct config 101", exit=126, stderr="homelab-collect: refused: pct config 101\n")
        result = lab.run("pve-discover", "--seed", "pve1")
        self.assertEqual(result.returncode, 1)
        self.assertIn("  101 ct pve1 running pihole (config not read)\n", result.stdout)
        self.assertIn("refused by the host's dispatcher", result.stderr)
        self.assertIn("bin/pve-collect-install", result.stderr)
        self.assertInventory(lab, "pve1", "pve1\npve2\n")

    def test_a_config_that_cannot_be_read_keeps_its_place(self):
        lab = fresh_lab(self)
        lab.respond("pve2", "qm config 200", exit=255, stderr="ssh: connection lost\n")
        result = lab.run("pve-discover", "--seed", "pve1")
        self.assertEqual(result.returncode, 1)
        self.assertIn(CT102 + "  200 vm pve2 running nas (config not read)\n", result.stdout)

    def test_a_guest_without_a_name_in_its_config_keeps_the_listed_name(self):
        lab = fresh_lab(self)
        lab.respond("pve1", "pct config 101", stdout=fx.CONFIGS["101"].replace("hostname: pihole\n", ""))
        result = lab.run("pve-discover", "--seed", "pve1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(CT101, result.stdout)

    def test_a_description_becomes_one_clean_line(self):
        lab = fresh_lab(self)
        banner = ("description: <div align='center'>%0A  <h2 style='font-size%3A 24px;'>Pi-hole LXC</h2>%0A"
                  "  <a href='https%3A//example.org'>Docs</a>%0A</div>%0A\n")
        lab.respond("pve1", "pct config 101", stdout=banner + fx.CONFIGS["101"] + "tags: dns;infra\n")
        result = lab.run("pve-discover", "--seed", "pve1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("  101 ct pve1 running pihole cores=1 memory=512 swap=512 disks=rootfs:8G tags=dns;infra"
                      " onboot=1\n    description: Pi-hole LXC Docs\n" + CT102, result.stdout)

    def test_a_storage_with_a_different_state_on_each_node(self):
        lab = fresh_lab(self)
        lab.respond("pve2", "pvesm status", stdout=fx.pvesm_status().replace("nfs     active", "nfs   inactive"))
        result = lab.run("pve-discover", "--seed", "pve1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("  nas-backup nfs pve1:active pve2:inactive\n", result.stdout)

    def test_a_storage_name_with_a_different_type_on_each_node(self):
        # independent nodes may reuse a storage name for another type
        lab = fresh_lab(self)
        lab.respond("pve2", "pvesm status", stdout=fx.pvesm_status().replace("     nfs ", "    cifs "))
        result = lab.run("pve-discover", "--seed", "pve1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("  nas-backup cifs pve2:active\n  nas-backup nfs pve1:active\n", result.stdout)

    def test_an_inventory_that_appears_during_the_run_is_not_replaced(self):
        # a path that exists at write time is never overwritten
        lab = fresh_lab(self)
        target = lab.root / "inventory" / "nodes"
        target.symlink_to(lab.root / "inventory" / "elsewhere")
        result = lab.run("pve-discover", "--seed", "pve1")
        self.assertEqual(result.returncode, 1)
        self.assertIn("inventory/nodes appeared during the run: nothing written", result.stderr)
        self.assertTrue(target.is_symlink())
        self.assertFalse((lab.root / "inventory" / "elsewhere").exists())
        self.assertEqual(sorted(p.name for p in (lab.root / "inventory").iterdir()), ["nodes"])

    def test_storages_or_guests_that_cannot_be_read_are_marked(self):
        lab = fresh_lab(self)
        lab.respond("pve2", "pvesm status", exit=255, stderr="ssh: connection lost\n")
        lab.respond("pve2", "qm list", exit=255, stderr="ssh: connection lost\n")
        result = lab.run("pve-discover", "--seed", "pve1")
        self.assertEqual(result.returncode, 1)
        self.assertIn("storages:\n  local dir pve1:active\n", result.stdout)
        self.assertIn("guests:\n" + CT101 + "guests not read: pve2\nstorages not read: pve2\n", result.stdout)
        self.assertInventory(lab, "pve1", "pve1\npve2\n")


def pvecm_nodes_with(*extra: str) -> dict:
    """pvecm nodes as each node prints it, with extra members after pve1 and pve2."""
    rows = "".join(f"         {i}          1 {name}\n" for i, name in enumerate(extra, start=3))
    return {"pve1": fx.PVECM_NODES.format(local1=" (local)", local2="") + rows,
            "pve2": fx.PVECM_NODES.format(local1="", local2=" (local)") + rows}


class ReconcileTest(unittest.TestCase):
    def setUp(self):
        self.lab = Lab()
        self.addCleanup(self.lab.close)
        fx.load(self.lab)

    def run_reconcile(self):
        before = inventory(self.lab)
        result = self.lab.run("pve-discover")
        self.assertEqual(inventory(self.lab), before)     # never written
        self.assertEqual(self.lab.commands("admin"), [])
        return result

    def test_an_inventory_that_matches(self):
        result = self.run_reconcile()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout,
                         f"pve-discover 1 | cluster lab\nnodes:\n  pve1 reachable {VERSION}\n"
                         f"  pve2 reachable {VERSION}\ninventory: unchanged\n" + STORAGES + GUESTS)

    def test_members_and_inventory_nodes_that_differ(self):
        self.lab.write_inventory("pve1\npve2\npve4\n")
        for node, text in pvecm_nodes_with("pve3").items():
            self.lab.respond(node, "pvecm nodes", stdout=text)
        result = self.run_reconcile()
        self.assertEqual(result.returncode, 1)
        self.assertIn("inventory: differs: +pve3 -pve4\n", result.stdout)
        self.assertIn(f"  pve3 {UNREACHABLE.format('pve3')}\n  pve4 {UNREACHABLE.format('pve4')}\n", result.stdout)
        self.assertTrue(result.stdout.endswith("guests not read: pve3\nguests not read: pve4\n"), result.stdout)

    def test_a_new_member_that_answers_is_read(self):
        for node, text in pvecm_nodes_with("pve3").items():
            self.lab.respond(node, "pvecm nodes", stdout=text)
        self.lab.aliases["pve3"] = {"role": "collect", "node": "pve3", "restricted": True}
        table = fx.answers("pve2")
        table["pct list"] = fx.ok(fx.pct_list([]))
        table["qm list"] = fx.ok("")
        self.lab.responses["pve3"] = table
        result = self.run_reconcile()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"  pve3 reachable {VERSION}\ninventory: differs: +pve3\n", result.stdout)
        self.assertIn("  local dir pve1:active pve2:active pve3:active\n", result.stdout)
        self.assertIn(GUESTS, result.stdout)

    def test_a_member_with_an_invalid_name_is_marked_not_added(self):
        for node, text in pvecm_nodes_with("bad_name").items():
            self.lab.respond(node, "pvecm nodes", stdout=text)
        result = self.run_reconcile()
        self.assertEqual(result.returncode, 1)
        self.assertIn("  bad_name invalid name\n", result.stdout)
        self.assertIn("inventory: unchanged\n", result.stdout)

    def test_an_inventory_node_that_does_not_answer_is_still_a_member(self):
        self.lab.unreachable("pve2")
        result = self.run_reconcile()
        self.assertEqual(result.returncode, 1)
        self.assertIn(f"  pve2 {UNREACHABLE.format('pve2')}\ninventory: unchanged\n", result.stdout)
        self.assertTrue(result.stdout.endswith("guests:\n" + CT101 + "guests not read: pve2\n"), result.stdout)

    def test_no_member_list_can_be_read(self):
        self.lab.unreachable("pve1")
        self.lab.unreachable("pve2")
        result = self.run_reconcile()
        self.assertEqual(result.returncode, 1)
        self.assertTrue(result.stdout.startswith("pve-discover 1 | unknown\n"), result.stdout)
        self.assertIn("inventory: not compared (no member list could be read)\n", result.stdout)

    def test_independent_standalone_nodes_are_one_inventory(self):
        fx.standalone(self.lab, "pve1")
        fx.standalone(self.lab, "pve2")
        result = self.run_reconcile()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.startswith("pve-discover 1 | standalone\n"), result.stdout)
        self.assertIn("inventory: unchanged\n", result.stdout)

    def test_the_same_vmid_on_two_independent_nodes_gives_two_lines(self):
        fx.standalone(self.lab, "pve1")
        fx.standalone(self.lab, "pve2")
        self.lab.respond("pve2", "pct list", stdout=fx.pct_list([("101", "stopped", "pihole")]))
        self.lab.respond("pve2", "qm list", stdout="")
        self.lab.respond("pve2", "pct config 101", stdout=fx.CONFIGS["101"])
        result = self.run_reconcile()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("guests:\n" + CT101 +
                      "  101 ct pve2 stopped pihole cores=1 memory=512 swap=512 disks=rootfs:8G onboot=1\n",
                      result.stdout)

    def test_inventory_names_that_are_not_proxmox_names_show_as_differences(self):
        # inventory/nodes allows any node name, with its alias in a column
        self.lab.write_inventory("lab-a pve1 lab-a-admin\npve2\n")
        result = self.run_reconcile()
        self.assertIn("inventory: differs: +pve1 -lab-a\n", result.stdout)
        # lab-a said it is pve1, so pve1 is neither probed nor unknown
        self.assertIn(f"  lab-a (Proxmox name pve1) reachable {VERSION}\n", result.stdout)
        self.assertNotIn("pve1 unreachable", result.stdout)
        self.assertNotIn("not read", result.stdout)
        self.assertIn("  101 ct lab-a running pihole", result.stdout)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_the_report_is_byte_identical_across_runs(self):
        self.assertEqual(self.run_reconcile().stdout, self.run_reconcile().stdout)

    def test_a_member_list_that_cannot_be_read_is_marked(self):
        # exit 1 must come with a line in the report
        self.lab.respond("pve2", "pvecm nodes", exit=126, stderr="homelab-collect: refused: pvecm nodes\n")
        result = self.run_reconcile()
        self.assertEqual(result.returncode, 1)
        self.assertIn("inventory: unchanged\n", result.stdout)
        self.assertTrue(result.stdout.endswith("members not read: pve2\n"), result.stdout)
        # the message names the read that failed, and the refusal gets its hint
        self.assertIn("could not read the cluster members of pve2 (pvecm nodes, exit 126)", result.stderr)
        self.assertIn("re-run bin/pve-collect-install on that node", result.stderr)

    def test_an_independent_node_whose_member_list_cannot_be_read_is_not_removed(self):
        # the node answered, so it is not "-pve2"
        fx.standalone(self.lab, "pve1")
        fx.standalone(self.lab, "pve2")
        self.lab.respond("pve2", "ls /etc/pve/nodes", stdout="")
        result = self.run_reconcile()
        self.assertEqual(result.returncode, 1)
        self.assertIn("inventory: unchanged\n", result.stdout)
        self.assertNotIn("-pve2", result.stdout)
        self.assertTrue(result.stdout.endswith(GUESTS + "members not read: pve2\n"), result.stdout)

if __name__ == "__main__":
    unittest.main()
