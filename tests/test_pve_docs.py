import re
import subprocess
import unittest

from tests import ROOT

TOOLS = ["pve-state", "pve-health", "pve-capacity", "pve-selftest", "pve-discover", "pve-snapshot", "pve-backup",
         "pve-update-host", "pve-update-ct", "pve-cleanup", "pve-move-disk", "pve-repo-setup",
         "pve-collect-install"]


class DocsTest(unittest.TestCase):
    def test_guide_covers_every_tool_and_the_api(self):
        guide = (ROOT / "docs" / "proxmox-toolkit.md").read_text()
        for tool in TOOLS:
            self.assertIn(f"bin/{tool}", guide)
        for name in ("pve_collect", "pve_admin", "pve_plan_add", "pve_plan_execute", "pve_require_api",
                     "local/collect.allow", "local/selftest.d", "{aptfile}", "PVE_LIB_API"):
            self.assertIn(name, guide)

    def test_every_tool_has_help(self):
        for tool in TOOLS:
            with self.subTest(tool=tool):
                result = subprocess.run(["bash", str(ROOT / "bin" / tool), "--help"], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0)
                self.assertTrue(result.stdout.startswith(f"Usage: {tool}"))

    def test_ssh_guide_points_to_the_shipped_dispatcher(self):
        guide = (ROOT / "docs" / "ssh-access.md").read_text()
        self.assertIn("bin/pve-collect-install", guide)
        self.assertIn("HOMELAB_SSHPASS=1", guide)
        self.assertNotIn('read -r -a argv <<< "$cmd"', guide)   # the inline script is gone

    def test_every_host_block_turns_connection_sharing_off(self):
        guide = (ROOT / "docs" / "ssh-access.md").read_text()
        blocks = re.findall(r"(?ms)^ *Host pve1(?:-admin)?\n.*?(?=^ *```)", guide)
        self.assertGreaterEqual(len(blocks), 3)
        for block in blocks:
            self.assertIn("ControlMaster no", block)
            self.assertIn("ControlPath none", block)
        self.assertIn("ControlMaster=no", (ROOT / "docs" / "proxmox-toolkit.md").read_text())

    def test_sudo_rule_covers_every_allowlisted_command(self):
        guide = (ROOT / "docs" / "ssh-access.md").read_text()
        self.assertNotIn("/usr/sbin/pct list, /usr/sbin/pct config *", guide)   # the partial example is gone
        self.assertIn("refused (sudo)", guide)
        self.assertIn("s/{[a-z]*}/*/g", guide)
        self.assertIn("refused (sudo)", (ROOT / "docs" / "proxmox-toolkit.md").read_text())

    def test_docs_state_the_toolkit_rules(self):
        guide = (ROOT / "docs" / "proxmox-toolkit.md").read_text()
        for phrase in ("--node NODE", "pass --node NODE", "corosync.conf", "may belong to a snapshot",
                       "log in as **root**", "dpkg --configure -a", "support is experimental", "refused (sudo)",
                       "no summary line", "Proxmox Backup Server", "bin/pve-discover --seed pve1",
                       "Bash(bin/pve-discover:*)", "PVE_QUORUM_LOCAL", "pve_inventory_add"):
            self.assertIn(phrase, guide)
        readme = (ROOT / "README.md").read_text()
        self.assertIn("--dry-run` first", readme)
        self.assertIn("support is experimental", readme)
        self.assertIn("bin/pve-discover --seed pve1", readme)
        self.assertNotIn("Discovery: bootstrap the wiki", readme)
        skill = (ROOT / ".claude" / "skills" / "infra-change" / "SKILL.md").read_text()
        # the Proxmox note sits inside the plan, not between "Wait for an explicit yes." and "Then create"
        self.assertRegex(skill, r"Wait\s+for an explicit yes\. Then create `wiki/changes/")

    def test_agents_and_readme_mention_the_toolkit(self):
        agents = (ROOT / "AGENTS.md").read_text()
        readme = (ROOT / "README.md").read_text()
        for text in (agents, readme):
            self.assertIn("remote/", text)
            self.assertIn("bin/pve-", text)
        self.assertIn("--yes", agents)
        self.assertNotRegex(readme, r"(?m)^- A generic Proxmox toolkit")

    def test_the_infra_change_skill_names_the_collector(self):
        self.assertIn("bin/pve-state", (ROOT / ".claude" / "skills" / "infra-change" / "SKILL.md").read_text())

    def test_guide_documents_the_hardened_behavior(self):
        guide = (ROOT / "docs" / "proxmox-toolkit.md").read_text()
        for phrase in ("could not read", "Remv", "lock:", "recovery:", "root:root", "pve_guest_has_snapshot"):
            self.assertIn(phrase, guide)


class DiscoverDocsTest(unittest.TestCase):
    def test_the_discover_operation_is_documented(self):
        skill = (ROOT / ".claude" / "skills" / "llm-wiki" / "SKILL.md").read_text()
        self.assertIn("| DISCOVER |", skill)
        ops = (ROOT / ".claude" / "skills" / "llm-wiki" / "references" / "operations.md").read_text()
        for phrase in ("## DISCOVER", "bin/pve-discover --seed", "wiki-capture discovery --file",
                       "unknown, not removed", "analyses/<date>-reconciliation.md", "Change without a record",
                       "`unchanged:` alone is not enough", "discovery-<HHMM>", 'tmp="$(mktemp)"',
                       "a `-<node>` whose node line says `unreachable`", "the directory of an old name"):
            self.assertIn(phrase, ops)

    def test_the_toolkit_guide_explains_the_uncertain_differences(self):
        guide = " ".join((ROOT / "docs" / "proxmox-toolkit.md").read_text().split())
        for phrase in ("A `-<node>` whose node line says `unreachable` is unknown too",
                       "`<node> (Proxmox name <name>)`", "the directory of an old name"):
            self.assertIn(phrase, guide)

    def test_the_schema_points_guests_to_the_overview_table(self):
        schema = (ROOT / "templates" / "wiki" / "AGENTS.md").read_text()
        self.assertIn("point to the guest table in `overview.md` instead", schema)
        self.assertNotIn("point to your inventory instead", schema)

    def test_the_example_overview_has_a_guest_table(self):
        overview = (ROOT / "examples" / "wiki" / "overview.md").read_text()
        self.assertIn("## Guests", overview)
        self.assertIn("| CT 105 | `media` | pve1 |", overview)
        self.assertIn("[[sources/2026-06-01-guests]]", overview)

if __name__ == "__main__":
    unittest.main()
