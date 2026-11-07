import unittest

from tests.toolkit import Lab


class InventoryTest(unittest.TestCase):
    def setUp(self):
        self.lab = Lab()
        self.addCleanup(self.lab.close)

    def load(self, text: str, show: str):
        self.lab.write_inventory(text)
        return self.lab.bash("pve_inventory_load\n" + show)

    def test_alias_defaults_and_explicit_columns(self):
        result = self.load("pve1\npve2 pve2-ro pve2-root\n",
                           'for n in pve1 pve2; do _pve_alias_of $n collect; c=$REPLY; '
                           '_pve_alias_of $n admin; echo "$n $c $REPLY"; done')
        self.assertEqual(result.stdout, "pve1 pve1 pve1-admin\npve2 pve2-ro pve2-root\n")

    def test_nodes_are_sorted(self):
        result = self.load("pve2\npve1\n", "pve_nodes")
        self.assertEqual(result.stdout, "pve1\npve2\n")

    def test_tabs_comments_and_crlf(self):
        result = self.load("pve1\t# main node\r\n# whole-line comment\r\n\r\n  pve2  \r\n", "pve_nodes")
        self.assertEqual((result.returncode, result.stdout), (0, "pve1\npve2\n"), result.stderr)

    def test_errors_name_the_line(self):
        cases = {
            "pve1\npve_1\n": "inventory/nodes:2: invalid name 'pve_1'",
            "pve1\npve1\n": "inventory/nodes:2: node 'pve1' listed twice",
            "pve1 a b c\n": "inventory/nodes:1: expected 'node [collect] [admin]'",
            "pve1 same same\n": "inventory/nodes:1: the collect and admin aliases must differ",
            "# nothing\n": "inventory/nodes: no node listed",
            "pve1 a a-admin\npve2 a b\n": "inventory/nodes:2: alias 'a' is already used by node 'pve1'",
            "pve1 x y\npve2 y z\n": "inventory/nodes:2: alias 'y' is already used by node 'pve1'",
            "pve1\npve1-admin\n": "inventory/nodes:2: alias 'pve1-admin' is already used by node 'pve1'",
        }
        for text, message in cases.items():
            with self.subTest(text=text):
                result = self.load(text, "true")
                self.assertEqual(result.returncode, 2)
                self.assertIn(message, result.stderr)

    def test_missing_inventory(self):
        (self.lab.root / "inventory" / "nodes").unlink()
        result = self.lab.bash("pve_inventory_load")
        self.assertEqual(result.returncode, 2)
        self.assertIn("no inventory: create inventory/nodes", result.stderr)

    def test_unknown_node(self):
        result = self.load("pve1\n", "pve_require_node pve9")
        self.assertEqual(result.returncode, 2)
        self.assertIn("unknown node 'pve9'", result.stderr)


    def test_in_memory_inventory(self):
        result = self.lab.bash(
            "pve_inventory_reset\npve_inventory_add pve2\npve_inventory_add pve1 lab1\npve_nodes\n"
            'for n in pve1 pve2; do _pve_alias_of $n collect; c=$REPLY; _pve_alias_of $n admin; echo "$n $c $REPLY"; done\n'
            'pve_alias_owner lab1 && echo "lab1 $REPLY"\n'
            'pve_alias_owner pve2-admin && echo "pve2-admin $REPLY"\n'
            'pve_alias_owner pve3 || echo "pve3 free"\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "pve1\npve2\npve1 lab1 pve1-admin\npve2 pve2 pve2-admin\n"
                                        "lab1 pve1\npve2-admin pve2\npve3 free\n")

    def test_in_memory_inventory_errors(self):
        cases = {
            "pve_inventory_add 'bad name'": "invalid name 'bad name'",
            "pve_inventory_add pve1; pve_inventory_add pve1": "node 'pve1' listed twice",
            "pve_inventory_add pve1 lab1; pve_inventory_add pve2 lab1": "alias 'lab1' is already used by node 'pve1'",
            "pve_inventory_add pve1 pve1-admin": "the collect and admin aliases must differ ('pve1-admin')",
        }
        for script, message in cases.items():
            with self.subTest(script=script):
                result = self.lab.bash("pve_inventory_reset\n" + script)
                self.assertEqual(result.returncode, 2)
                self.assertIn(message, result.stderr)

    def test_reset_empties_a_loaded_inventory(self):
        result = self.load("pve1\npve2\n", 'pve_inventory_reset\necho "${#PVE_NODE_LIST[@]}"\n'
                                           "pve_node_known pve1 || echo unknown\npve_alias_owner pve1 || echo free")
        self.assertEqual(result.stdout, "0\nunknown\nfree\n")

class InitTest(unittest.TestCase):
    def setUp(self):
        self.lab = Lab()
        self.addCleanup(self.lab.close)

    def test_root_and_api(self):
        result = self.lab.bash('echo "$PVE_ROOT $PVE_LIB_API"; pve_require_api 1')
        self.assertEqual(result.stdout.strip(), f"{self.lab.root} 1")

    def test_wrong_api_is_a_clear_error(self):
        result = self.lab.bash("pve_require_api 2")
        self.assertEqual(result.returncode, 2)
        self.assertIn("needs lib/pve API 2", result.stderr)

    def test_init_loads_env_inventory_and_audit(self):
        self.lab.write_env("PVE_BACKUP_STORAGE=nas-backup\n")
        result = self.lab.bash('pve_init demo a b; echo "$PVE_BACKUP_STORAGE ${PVE_NODE_LIST[*]}"')
        self.assertEqual(result.stdout.strip(), "nas-backup pve1 pve2")
        self.assertIn("tool: demo", self.lab.audit_text())

    def test_sourcing_twice_is_harmless(self):
        result = self.lab.bash("source lib/pve/init.sh; echo ok")
        self.assertEqual(result.stdout.strip(), "ok")


if __name__ == "__main__":
    unittest.main()
