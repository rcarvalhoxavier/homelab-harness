"""What a visitor sees first: the README, the agent guide and the CI gate."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def readme() -> str:
    return (ROOT / "README.md").read_text()


class ReadmeTest(unittest.TestCase):
    def test_the_first_screen_shows_the_agent_answering_with_a_source(self):
        head = readme().split("## What's inside")[0]
        self.assertIn("Is the Pi-hole pair actually redundant?", head)
        self.assertIn("analyses/2026-06-20-pihole-pair-redundancy", head)
        self.assertIn("sources/2026-06-20-pihole-pair", head)
        self.assertNotIn("Claude", head.split("```")[1])  # the demo block itself is agent-neutral

    def test_the_demo_cites_pages_that_exist_in_the_example_wiki(self):
        for page in ("analyses/2026-06-20-pihole-pair-redundancy.md", "sources/2026-06-20-pihole-pair.md"):
            self.assertTrue((ROOT / "examples" / "wiki" / page).is_file(), page)

    def test_the_first_screen_says_what_to_try_first(self):
        head = readme().split("## What's inside")[0]
        self.assertIn("**Try it**", head)
        self.assertIn("bin/wiki-lint --wiki examples/wiki", head)

    def test_the_opening_says_the_toolkit_is_for_proxmox_ve(self):
        opening = readme().split("```")[0]
        self.assertIn("Proxmox VE", opening)

    def test_the_toolkit_row_counts_the_tools_in_bin(self):
        self.assertEqual(len(list((ROOT / "bin").glob("pve-*"))), 13)
        self.assertIn("five read-only tools", readme())
        self.assertIn("eight changing tools", readme())

    def test_superpowers_is_introduced_with_its_installation(self):
        text = readme()
        self.assertIn("https://github.com/obra/superpowers", text)
        self.assertIn("/plugin install superpowers@claude-plugins-official", text)

    def test_the_readme_ends_with_contributing_not_a_note_to_the_maintainer(self):
        self.assertIn("## Contributing", readme())
        self.assertNotIn("For maintainers of the template", readme())
        self.assertNotIn("Watch the first run", readme())


class AgentsGuideTest(unittest.TestCase):
    def test_other_agents_learn_where_a_skill_lives(self):
        self.assertIn("`.claude/skills/<name>/SKILL.md`", (ROOT / "AGENTS.md").read_text())

    def test_superpowers_is_optional_in_the_routing(self):
        guide = (ROOT / "AGENTS.md").read_text()
        self.assertIn("superpowers, if installed", guide)


UPSTREAM = "github.repository == 'rcarvalhoxavier/homelab-harness'"


class CiGateTest(unittest.TestCase):
    def test_the_framework_jobs_run_in_the_upstream_repository_and_copies_run_their_own(self):
        ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
        self.assertEqual(ci.count(f"if: {UPSTREAM}"), 2)  # framework, sshd
        self.assertEqual(ci.count("if: github.repository != 'rcarvalhoxavier/homelab-harness'"), 1)  # instance
