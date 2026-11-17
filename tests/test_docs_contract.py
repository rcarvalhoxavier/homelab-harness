"""The guides and the skills agree with the code and with each other.

These tests do not look for phrases. They read the commands, the SSH config blocks and the
permission rules that the documents give the reader, and check them against the real dispatcher,
against the steps that create each key and alias, and against the tools in bin/.
"""
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests import ROOT

DISPATCHER = ROOT / "remote" / "homelab-collect"
SSH_GUIDE = ROOT / "docs" / "ssh-access.md"
# Documents whose text is addressed to the reader or to the agent. Tests are not documents.
DOCS = sorted({ROOT / "README.md", ROOT / "AGENTS.md", *ROOT.glob("docs/*.md"),
               *ROOT.glob(".claude/skills/**/*.md"), *ROOT.glob("templates/**/*.md")})
# Read-only tools that still must ask: one can connect through the admin alias and run the
# executable files of local/selftest.d, the other writes inventory/nodes with --seed.
ASKS_EVERY_TIME = {"pve-selftest", "pve-discover"}


def fenced_blocks(path: Path):
    """Yield (language, first line number, lines) of each fenced block in a Markdown file."""
    block, language, start = None, "", 0
    for number, line in enumerate(path.read_text().splitlines(), 1):
        if line.lstrip().startswith("```"):
            if block is None:
                block, language, start = [], line.strip()[3:].strip(), number + 1
            else:
                yield language, start, block
                block = None
        elif block is not None:
            block.append(line)


def collect_commands(path: Path) -> list[str]:
    """Commands the document sends to a node through a collect alias.

    Covers `ssh <alias> <command>` in code blocks and in inline code, and the commands of the
    "Proxmox node" and "Proxmox guest" rows of the collectors table. Admin aliases and examples
    that chain commands (shown to be refused) are left out.
    """
    text = path.read_text()
    spans = [line for _, _, lines in fenced_blocks(path) for line in lines]
    spans += re.findall(r"`([^`\n]+)`", text)
    found = []
    for span in spans:
        match = re.match(r"\s*ssh (?!-)(\S+) (.+?)\s*(#.*)?$", span)
        if not match or match.group(1).endswith("-admin") or "&&" in match.group(2):
            continue
        found.append(re.split(r"\s+\|\s+", match.group(2))[0])   # what follows a pipe runs here
    for row in re.findall(r"^\| Proxmox (?:node|guest) \| (.+) \|$", text, re.M):
        found += re.findall(r"`([^`]+)`", row)
    return [command.replace("<id>", "101") for command in found]


class CollectCommandsTest(unittest.TestCase):
    def verdict(self, etc: Path, command: str) -> str:
        return subprocess.run(["bash", str(DISPATCHER), "--etc", str(etc), "--match", command],
                              capture_output=True, text=True).stdout.strip()

    def test_every_documented_collect_command_is_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            etc = Path(tmp)
            (etc / "framework.allow").write_text((ROOT / "remote" / "collect.allow").read_text())
            (etc / "local.allow").write_text("")
            seen = 0
            for path in DOCS:
                for command in collect_commands(path):
                    seen += 1
                    with self.subTest(document=path.name, command=command):
                        self.assertEqual(self.verdict(etc, command), "allowed")
            self.assertGreater(seen, 8, "the extraction found too few commands to mean anything")


class SshGuideTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lines = SSH_GUIDE.read_text().splitlines()
        cls.blocks = list(fenced_blocks(SSH_GUIDE))

    def test_every_identity_file_is_created_by_a_keygen_of_the_guide(self):
        made = {m.group(1) for _, _, lines in self.blocks for line in lines
                if (m := re.search(r"ssh-keygen .*-f (\S+)", line))}
        used = {m.group(1) for _, _, lines in self.blocks for line in lines
                if (m := re.match(r"\s*IdentityFile (\S+)", line))}
        self.assertTrue(used)
        self.assertEqual(sorted(used - made), [])

    def test_every_installed_key_is_created_before_it_is_installed(self):
        made = {}
        for _, start, lines in self.blocks:
            for offset, line in enumerate(lines):
                if m := re.search(r"ssh-keygen .*-f (\S+)", line):
                    made.setdefault(m.group(1), start + offset)
                if m := re.search(r"ssh-copy-id -i (\S+)\.pub", line):
                    with self.subTest(key=m.group(1)):
                        self.assertLess(made.get(m.group(1), 10**6), start + offset)

    def test_every_alias_is_defined_before_the_first_command_that_uses_it(self):
        defined, uses = {}, {}
        for language, start, lines in self.blocks:
            for offset, line in enumerate(lines):
                number = start + offset
                if language == "sshconfig":
                    if m := re.match(r"\s*Host (\S+)", line):
                        defined.setdefault(m.group(1), number)
                    continue
                for pattern, aliases in (
                        (r"\bssh (?:-o \S+ )*(?!-)([\w-]+) ", lambda a: {a}),
                        (r"bin/pve-collect-install ([\w-]+)", lambda a: {a, a + "-admin"}),
                        (r"bin/pve-selftest .*--node ([\w-]+)", lambda a: {a})):
                    if m := re.search(pattern, line):
                        for alias in aliases(m.group(1)):
                            uses.setdefault(alias, number)
        self.assertTrue(uses)
        for alias, number in sorted(uses.items()):
            with self.subTest(alias=alias):
                self.assertLess(defined.get(alias, 10**6), number)


class PreApprovalTest(unittest.TestCase):
    @staticmethod
    def changing_tools() -> set[str]:
        """The changing tools, as AGENTS.md lists them in its safety rules."""
        text = (ROOT / "AGENTS.md").read_text()
        sentence = re.search(r"run a changing tool \((.+?)\)", text, re.S).group(1)
        tools = set()
        for name in re.findall(r"`(?:bin/)?(pve-[a-z*-]+)`", sentence):
            tools |= {p.name for p in (ROOT / "bin").glob(name)}
        return tools

    def test_the_changing_tools_are_the_eight_of_agents_md(self):
        self.assertEqual(len(self.changing_tools()), 8)

    def test_exactly_one_document_holds_the_list(self):
        holders = [p.relative_to(ROOT) for p in DOCS if "Bash(bin/" in p.read_text()]
        self.assertEqual([str(p) for p in holders], ["docs/ssh-access.md"])

    def test_the_list_names_only_tools_that_change_nothing_and_run_no_local_code(self):
        entries = re.findall(r"Bash\(bin/([\w-]+):\*\)", SSH_GUIDE.read_text())
        self.assertTrue(entries)
        refused = self.changing_tools() | ASKS_EVERY_TIME
        for tool in entries:
            with self.subTest(tool=tool):
                self.assertTrue((ROOT / "bin" / tool).is_file())
                self.assertNotIn(tool, refused)

    def test_agents_md_says_pve_selftest_is_never_pre_approved(self):
        text = (ROOT / "AGENTS.md").read_text()
        sentence = re.search(r"Never pre-approve.+?\.", text, re.S).group(0)
        self.assertIn("pve-selftest", sentence)


if __name__ == "__main__":
    unittest.main()
