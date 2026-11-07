import datetime
import time
import unittest

from tests import pvefixtures as fx
from tests.toolkit import Lab


class ParserTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lab = Lab()

    @classmethod
    def tearDownClass(cls):
        cls.lab.close()

    def parse(self, call: str, stdin: str = "") -> str:
        result = self.lab.shell("source lib/pve/parse.sh\n" + call, stdin=stdin)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def out(self, node: str, command: str, version: str = "8") -> str:
        return fx.answers(node, version)[command]["stdout"]

    def test_pct_list_with_and_without_a_lock(self):
        text = self.out("pve1", "pct list") + "103        running    backup       grafana             \n" \
                                              "104        stopped                              \n"
        self.assertEqual(self.parse("pve_parse_pct_list", text),
                         "101 running pihole\n103 running grafana\n104 stopped -\n")

    def test_qm_list(self):
        self.assertEqual(self.parse("pve_parse_qm_list", self.out("pve2", "qm list")), "200 running nas\n")
        self.assertEqual(self.parse("pve_parse_qm_list", ""), "")

    def test_qm_list_with_a_vm_that_has_no_name(self):
        # Proxmox lists a VM without a name as "VM <vmid>"
        text = self.out("pve2", "qm list") + "       201 VM 201               stopped    2048              32.00 0\n"
        self.assertEqual(self.parse("pve_parse_qm_list", text), "200 running nas\n201 stopped -\n")

    def test_pvesm_status(self):
        text = self.out("pve1", "pvesm status") + \
            "old-nfs            nfs   inactive               0               0               0    0.00%\n" \
            "off           lvmthin   disabled               0               0               0      N/A\n" \
            "comma              dir     active        100              50              50   50,25%\n"
        self.assertEqual(self.parse("pve_parse_pvesm_status", text),
                         "local dir active 98497780 13120440 80327792 13.32\n"
                         "local-lvm lvmthin active 365760512 100022210 265738302 27.35\n"
                         "nas-backup nfs active 1951350784 512340224 1439010560 26.26\n"
                         "old-nfs nfs inactive 0 0 0 -\n"
                         "off lvmthin disabled 0 0 0 -\n"
                         "comma dir active 100 50 50 50.25\n")

    def test_pvesm_list(self):
        self.assertEqual(self.parse("pve_parse_pvesm_list", self.out("pve1", "pvesm list local")),
                         "local:vztmpl/debian-12-standard_12.7-1_amd64.tar.zst tzst vztmpl 126030062 -\n")
        self.assertIn("local-lvm:vm-200-disk-0 raw images 34359738368 200\n",
                      self.parse("pve_parse_pvesm_list", self.out("pve2", "pvesm list local-lvm")))

    def test_lvm_and_zfs(self):
        self.assertEqual(self.parse("pve_parse_lvs_thinpools", "  pve data 374538764288,00 89,34 1,87\n"),
                         "pve data 374538764288 89.34 1.87\n")
        self.assertEqual(self.parse("pve_parse_lvs_thinpools", "  pve data 374538764288\n"),
                         "pve data 374538764288 - -\n")
        self.assertEqual(self.parse("pve_parse_lvs", "  vm-9-disk-0 pve 8589934592\n"),
                         "vm-9-disk-0 pve 8589934592 -\n")
        self.assertEqual(self.parse("pve_parse_lvs", self.out("pve1", fx.LVS_ALL)),
                         "data pve 374538764288 27.35\nroot pve 103079215104 -\nswap pve 8589934592 -\n"
                         "vm-101-disk-0 pve 8589934592 41.20\n")
        self.assertEqual(self.parse("pve_parse_vgs", "  pve 17179869184\n"), "pve 17179869184\n")
        self.assertEqual(self.parse("pve_parse_zpool", "rpool\t999653638144\t123456789012\t876196849132\t12\tONLINE\n"),
                         "rpool 999653638144 123456789012 876196849132 12 ONLINE\n")
        self.assertEqual(self.parse("pve_parse_zpool", "no pools available\n"), "")

    def test_cluster(self):
        self.assertEqual(self.parse("pve_parse_pvecm_status", self.out("pve1", "pvecm status")), "2 2 Yes\n")
        result = self.lab.shell("source lib/pve/parse.sh\npve_parse_pvecm_status", stdin="")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.parse("pve_parse_pvecm_nodes", self.out("pve2", "pvecm nodes")), "pve1\npve2\n")

    def test_storage_cfg(self):
        text = fx.STORAGE_CFG + "\ndir: shared-dir\n\tpath /srv\n\tshared 1\n\tnodes pve1,pve3\n\tcontent images\n"
        self.assertEqual(self.parse("pve_parse_storage_cfg", text),
                         "local|dir||||iso,vztmpl,backup\n"
                         "local-lvm|lvmthin|||pve|rootdir,images\n"
                         "nas-backup|nfs||||backup\n"
                         "shared-dir|dir|pve1,pve3|1||images\n")

    def test_snapshots(self):
        self.assertEqual(self.parse("pve_parse_snapshots", fx.SNAPSHOTS["101"]),
                         "pre-upgrade 2026-06-01T10:00:00\n")
        self.assertEqual(self.parse("pve_parse_snapshots", fx.SNAPSHOTS["200"]), "")
        self.assertIn("\n `-> current ", fx.SNAPSHOTS["101"])
        for indent in (" ", "    "):
            listed = fx.SNAPSHOTS["101"].replace("\n `-> current", "\n" + indent + "`-> current")
            self.assertEqual(self.parse("pve_parse_snapshots", listed), "pre-upgrade 2026-06-01T10:00:00\n")

    def test_config_volumes_and_values(self):
        self.assertEqual(self.parse("pve_parse_config_volumes", fx.CONFIGS["200"]),
                         "scsi0 local-lvm vm-200-disk-0 32G\n")
        config = fx.CONFIGS["101"] + "mp0: /srv/data,mp=/data\nmp1: local-lvm:vm-101-disk-1,mp=/var,size=4G\n" \
                                     "unused0: local-lvm:vm-101-disk-2\n"
        self.assertEqual(self.parse("pve_parse_config_volumes", config),
                         "rootfs local-lvm vm-101-disk-0 8G\nmp1 local-lvm vm-101-disk-1 4G\n"
                         "unused0 local-lvm vm-101-disk-2 -\n")
        self.assertEqual(self.parse("pve_parse_config_volumes", "nvme0: local-lvm:vm-5-disk-0,size=16G\n"),
                         "nvme0 local-lvm vm-5-disk-0 16G\n")
        self.assertEqual(self.parse("pve_config_value ostype", fx.CONFIGS["101"]), "debian\n")

    def test_host_figures(self):
        self.assertEqual(self.parse("pve_parse_free", self.out("pve1", "free -b")),
                         "33454669824 10737418240 8589930496 0\n")
        self.assertEqual(self.parse("pve_parse_df", self.out("pve1", "df -P -B1 /")),
                         "101203873792 13435469824 82580643840 14\n")
        self.assertEqual(self.parse("pve_parse_upgradable", self.out("pve1", "apt list --upgradable")),
                         "pve-manager 8.4.1 8.4.2\nproxmox-kernel-6.8 6.8.12-10 6.8.12-11\n")
        self.assertEqual(self.parse("pve_parse_pkg_sim apt", fx.APT_SIM), "2\n")
        self.assertEqual(self.parse("pve_parse_pkg_sim apt", fx.APT_SIM_NONE), "0\n")
        self.assertEqual(self.parse("pve_parse_pkg_removals", fx.APT_SIM + "Remv proxmox-ve [8.4.0]\nRemv foo [1]\n"),
                         "proxmox-ve\nfoo\n")
        self.assertEqual(self.parse("pve_parse_pkg_removals", fx.APT_SIM), "")
        self.assertEqual(self.parse("pve_parse_new_kernels", fx.APT_SIM_NEW_KERNEL),
                         "proxmox-kernel-6.8.12-11-pve-signed\n")
        self.assertEqual(self.parse("pve_parse_new_kernels", fx.APT_SIM), "")
        self.assertEqual(self.parse("pve_parse_new_kernels",
                                    "Inst pve-kernel-5.15.158-2-pve (5.15.158-2 Proxmox:7.4/stable [amd64])\n"
                                    "Inst proxmox-kernel-helper [8.1.0] (8.1.1 Proxmox:8.4/stable [all])\n"),
                         "pve-kernel-5.15.158-2-pve\n")
        self.assertEqual(self.parse("pve_parse_pkg_sim apk",
                                    "(1/2) Upgrading musl (1.2.4-r2 -> 1.2.4-r3)\n"
                                    "(2/2) Installing ca-certificates (20240705-r0)\nOK: 9 MiB in 20 packages\n"),
                         "2\n")

    def test_versions_and_kernels(self):
        for version, major in (("8", "8"), ("9", "9")):
            with self.subTest(version=version):
                self.assertEqual(self.parse("pve_major_version", self.out("pve1", "pveversion", version)),
                                 major + "\n")
                self.assertEqual(self.parse("pve_newest_kernel", self.out("pve1", "ls /boot", version)),
                                 fx.VERSIONS[version]["newer"] + "\n")

    def test_backup_volid_types(self):
        self.assertEqual(self.parse("pve_backup_volid_type nas-backup:backup/vzdump-lxc-101-2026_06_30-23_00_02.tar.zst;"
                                    "pve_backup_volid_type nas-backup:backup/vzdump-qemu-200-2026_06_30-23_20_11.vma.zst"),
                         "ct\nvm\n")
        self.assertEqual(self.lab.shell("source lib/pve/parse.sh\npve_backup_volid_type local:iso/x.iso").returncode, 1)
        self.assertEqual(self.parse("pve_backup_volid_type pbs:backup/ct/101/2026-06-30T23:00:02Z;"
                                    "pve_backup_volid_type pbs:backup/vm/200/2026-06-30T23:20:11Z"), "ct\nvm\n")

    def test_pbs_backup_volid_dates(self):
        self.assertEqual(self.parse("pve_backup_volid_date pbs:backup/vm/200/2026-06-30T23:20:11Z"),
                         "2026-06-30T23:20:11\n")
        for bad in ("pbs:backup/ct/101/2026-06-30", "pbs:backup/ct/x/2026-06-30T23:20:11Z"):
            with self.subTest(bad=bad):
                self.assertEqual(self.lab.shell(f"source lib/pve/parse.sh\npve_backup_volid_date {bad}").returncode, 1)

    def test_dates_and_numbers(self):
        self.assertEqual(self.parse("pve_backup_volid_date "
                                    "nas-backup:backup/vzdump-qemu-200-2026_06_30-23_20_11.vma.zst"),
                         "2026-06-30T23:20:11\n")
        result = self.lab.shell("source lib/pve/parse.sh\npve_backup_volid_date local:iso/x.iso")
        self.assertEqual(result.returncode, 1)
        epoch = datetime.date(1970, 1, 1).toordinal()
        for day in ("1970-01-01", "2000-02-29", "2000-03-01", "2026-07-01", "2100-03-01"):
            with self.subTest(day=day):
                expected = datetime.date.fromisoformat(day).toordinal() - epoch
                self.assertEqual(self.parse(f"pve_days {day}"), f"{expected}\n")
        self.assertEqual(self.parse("pve_days 2026-06-30T23:20:11"), self.parse("pve_days 2026-06-30"))
        self.assertEqual(self.parse("pve_gib 8589934592"), "8.00\n")
        self.assertEqual(self.parse("if pve_num_gt 89.34 85; then echo yes; fi"), "yes\n")
        self.assertEqual(self.parse("if pve_num_gt 85 85; then echo yes; else echo no; fi"), "no\n")
        self.assertEqual(self.parse("pve_size_bytes 32G; pve_size_bytes 4M; pve_size_bytes 512"),
                         "34359738368\n4194304\n512\n")
        self.assertEqual(self.lab.shell("source lib/pve/parse.sh\npve_size_bytes 1.5G").returncode, 1)
        self.assertEqual(self.parse("pve_indent", "a\n\nb\n"), "  a\n  b\n")


    def test_cluster_name(self):
        self.assertEqual(self.parse("pve_parse_cluster_name", fx.COROSYNC), "lab\n")
        self.assertEqual(self.parse("pve_parse_cluster_name", "totem {\n  version: 2\n}\n"), "")

    def test_pvecm_local(self):
        self.assertEqual(self.parse("pve_parse_pvecm_local", self.out("pve2", "pvecm nodes")), "pve2\n")
        self.assertEqual(self.parse("pve_parse_pvecm_local", fx.PVECM_NODES.format(local1="", local2="")), "")

    def test_clean_description(self):
        banner = ("<div align='center'>%0A  <h2 style='font-size%3A 24px;'>Pi-hole LXC</h2>%0A"
                  "  <a href='https%3A//example.org' target='_blank'>Docs</a>%0A</div>%0A")
        words = ("word " * 50).strip()
        cases = {
            "disposable%3A homelab-harness acceptance%0A": "disposable: homelab-harness acceptance\n",
            banner: "Pi-hole LXC Docs\n",
            "100% sure, 50%off": "100% sure, 50%off\n",
            "caf%C3%A9 %E2%9D%A4": "café ❤\n",
            "  line one%0A%0A\tline two  ": "line one line two\n",
            "<br><p> </p>": "",
            words: words[:160].rstrip() + "…\n",
            "a%1B[31mred%07!": "a [31mred !\n",
            "a%00b": "ab\n",
            "back\\slash \\x41 \\c end": "back\\slash \\x41 \\c end\n",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(self.parse('pve_clean_description "$(cat)"', text), expected)

    def test_a_long_description_is_cleaned_in_linear_time(self):
        # a runbook-length note (20 KB) once took 10 s
        text = "%3Cp%3Eword%20and%20more%3C/p%3E%0A" * 600
        started = time.monotonic()
        self.assertEqual(self.parse('pve_clean_description "$(cat)"', text),
                         " ".join(["word and more"] * 13)[:160].rstrip() + "…\n")
        self.assertLess(time.monotonic() - started, 3)

    def test_clean_description_in_a_c_locale(self):
        # the bytes still decode when the admin machine has no UTF-8 locale
        result = self.lab.shell('source lib/pve/parse.sh\npve_clean_description "$(cat)"',
                                stdin="caf%C3%A9 ok", LC_ALL="C", LANG="C")
        self.assertEqual((result.returncode, result.stdout), (0, "café ok\n"), result.stderr)

    def test_the_cut_never_splits_a_character_in_a_c_locale(self):
        # a cut inside a multibyte character makes the capture invalid UTF-8
        for text, expected in (("a" * 159 + "%C3%A9bbbb", "a" * 159 + "…\n"),
                               ("a" * 158 + "%E2%9D%A4bbbb", "a" * 158 + "…\n"),
                               ("a" * 157 + "%E2%9D%A4bbbb", "a" * 157 + "❤…\n")):
            with self.subTest(text=text):
                result = self.lab.shell('source lib/pve/parse.sh\npve_clean_description "$(cat)"',
                                        stdin=text, LC_ALL="C", LANG="C")
                self.assertEqual((result.returncode, result.stdout), (0, expected), result.stderr)


class QuorumLocalTest(unittest.TestCase):
    def setUp(self):
        self.lab = Lab()
        self.addCleanup(self.lab.close)
        fx.load(self.lab)

    def local_of(self, node: str) -> str:
        result = self.lab.bash(f'pve_inventory_load\npve_quorum {node}\npve_quorum_members {node}\n'
                               'echo "members=$PVE_QUORUM_MEMBERS local=$PVE_QUORUM_LOCAL"')
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_the_local_member_of_a_cluster(self):
        self.assertEqual(self.local_of("pve1"), "members=pve1 pve2 local=pve1\n")
        self.assertEqual(self.local_of("pve2"), "members=pve1 pve2 local=pve2\n")

    def test_a_standalone_node_with_one_name_and_with_several(self):
        fx.standalone(self.lab, "pve1")
        self.assertEqual(self.local_of("pve1"), "members=pve1 local=pve1\n")
        self.lab.respond("pve1", "ls /etc/pve/nodes", stdout="old\npve1\n")
        self.assertEqual(self.local_of("pve1"), "members=old pve1 local=\n")

if __name__ == "__main__":
    unittest.main()
