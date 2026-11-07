import hashlib
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests import ROOT

DISPATCHER = ROOT / "remote" / "homelab-collect"

RULES = """\
# rules for the dispatcher tests
pct config {id}
pct listsnapshot {id}
pvesm list {storage} --content backup
cat /etc/pve/storage.cfg
cat {aptfile}
uname -r
id -u
printenv LC_ALL
printenv PATH
"""


class DispatcherTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.etc = Path(tmp.name)
        (self.etc / "framework.allow").write_text(RULES)
        (self.etc / "local.allow").write_text("pct exec 101 -- pihole -v\n")

    def run_cmd(self, command: str):
        env = {"PATH": os.environ["PATH"], "SSH_ORIGINAL_COMMAND": command}
        return subprocess.run(["bash", str(DISPATCHER), "--etc", str(self.etc)], env=env,
                              capture_output=True, text=True)

    def match(self, command: str) -> str:
        return subprocess.run(["bash", str(DISPATCHER), "--etc", str(self.etc), "--match", command],
                              capture_output=True, text=True).stdout.strip()

    def test_allowed_commands(self):
        for command in ("pct config 101", "pvesm list nas-backup --content backup",
                        "cat /etc/pve/storage.cfg", "cat /etc/apt/sources.list.d/pve-enterprise.sources",
                        "pct exec 101 -- pihole -v", "homelab-collect --version"):
            with self.subTest(command=command):
                self.assertEqual(self.match(command), "allowed")

    def test_refused_commands(self):
        for command in ("pct config 101; id", "pct config 101 && id", "pct config `id`",
                        "pct config $(id)", "pct config 101\nid", "pct config 101 --current",
                        "pct config 101x", "pct config", "cat /etc/pve/../shadow",
                        "cat /etc/apt/sources.list.d/../../shadow.list", "", " pct config 101",
                        "pct config 101 ", "pct  config 101", "pct config 'x'", "pct\tconfig 101",
                        "pct exec 102 -- pihole -v", "id", "bash", "pct config {id}"):
            with self.subTest(command=command):
                self.assertEqual(self.match(command), "refused")

    def test_runs_an_allowed_command_with_a_fixed_environment(self):
        self.assertEqual(self.run_cmd("uname -r").stdout, os.uname().release + "\n")
        self.assertEqual(self.run_cmd("printenv LC_ALL").stdout, "C\n")
        self.assertEqual(self.run_cmd("printenv PATH").stdout, "/usr/sbin:/usr/bin:/sbin:/bin\n")

    def test_refusal_has_the_marker_and_exit_126(self):
        result = self.run_cmd("rm -rf /")
        self.assertEqual(result.returncode, 126)
        self.assertEqual(result.stderr, "homelab-collect: refused: rm\\ -rf\\ /\n")
        self.assertEqual(self.run_cmd("").returncode, 126)

    def test_a_refused_command_is_echoed_quoted_on_one_line_and_truncated(self):
        result = self.run_cmd("pct config 101\nallowed: uname -r")
        self.assertEqual(result.returncode, 126)
        self.assertEqual(result.stderr, "homelab-collect: refused: $'pct config 101\\nallowed: uname -r'\n")
        long = self.run_cmd("x" * 5000)
        self.assertEqual(long.stderr, "homelab-collect: refused: " + "x" * 512 + "\n")

    def test_an_invalid_list_refuses_everything(self):
        for bad in ("pct config {vmid}\n", "cat /etc/x;y\n", "pct  config {id}\n",
                    "{storage} list\n", "pct exec {id} -- {storage} -v\n", "pct exec 101 -- {node}\n"):
            with self.subTest(bad=bad):
                (self.etc / "local.allow").write_text("# ok\n" + bad)
                result = self.run_cmd("uname -r")
                self.assertEqual(result.returncode, 126)
                self.assertIn(f"invalid allowlist line: {self.etc}/local.allow:2", result.stderr)

    def test_missing_lists_are_empty(self):
        (self.etc / "framework.allow").unlink()
        self.assertEqual(self.match("pct exec 101 -- pihole -v"), "allowed")
        self.assertEqual(self.match("uname -r"), "refused")

    def test_version_hashes_the_script_and_both_lists(self):
        data = DISPATCHER.read_bytes() + (self.etc / "framework.allow").read_bytes() \
            + (self.etc / "local.allow").read_bytes()
        expected = f"homelab-collect {hashlib.sha256(data).hexdigest()[:16]}\n"
        self.assertEqual(self.run_cmd("homelab-collect --version").stdout, expected)
        local = subprocess.run(["bash", str(DISPATCHER), "--etc", str(self.etc), "--version"],
                               capture_output=True, text=True)
        self.assertEqual(local.stdout, expected)

    def test_matching_ignores_the_inherited_locale(self):
        locales = {"C.UTF-8"}
        listed = subprocess.run(["locale", "-a"], capture_output=True, text=True).stdout.split()
        locales |= {name for name in listed if name.lower().startswith("en_us.utf")}
        for locale in sorted(locales):
            for command in ("pct config \u0661\u0662\u0663", "pct config \uff12", "pvesm list \u00e9x",
                            "pvesm list \ufb01le", "cat /etc/apt/sources.list.d/\u00e9.list"):
                with self.subTest(locale=locale, command=command):
                    env = {"PATH": os.environ["PATH"], "LC_ALL": locale}
                    out = subprocess.run(["bash", str(DISPATCHER), "--etc", str(self.etc), "--match", command],
                                         env=env, capture_output=True, text=True).stdout.strip()
                    self.assertEqual(out, "refused")

    def test_check_mode(self):
        good = subprocess.run(["bash", str(DISPATCHER), "--check", str(self.etc / "framework.allow")],
                              capture_output=True, text=True)
        self.assertEqual((good.returncode, good.stdout.strip()),
                         (0, f"{self.etc}/framework.allow: 9 rules"))
        (self.etc / "bad.allow").write_text("pct config {nope}\n")
        bad = subprocess.run(["bash", str(DISPATCHER), "--check", str(self.etc / "bad.allow")],
                             capture_output=True, text=True)
        self.assertEqual(bad.returncode, 1)
        self.assertIn("bad.allow:1", bad.stderr)

    def test_check_refuses_a_field_where_a_program_name_goes(self):
        for bad in ("{id} config\n", "pct exec {id} -- {snap} status\n"):
            with self.subTest(bad=bad):
                (self.etc / "bad.allow").write_text(bad)
                result = subprocess.run(["bash", str(DISPATCHER), "--check", str(self.etc / "bad.allow")],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 1)
                self.assertIn("bad.allow:1", result.stderr)
        (self.etc / "ok.allow").write_text("pct exec {id} -- pihole status\n")
        ok = subprocess.run(["bash", str(DISPATCHER), "--check", str(self.etc / "ok.allow")],
                            capture_output=True, text=True)
        self.assertEqual(ok.returncode, 0, ok.stderr)

    def test_framework_list_is_valid(self):
        result = subprocess.run(["bash", str(DISPATCHER), "--check", str(ROOT / "remote" / "collect.allow")],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipIf(os.geteuid() == 0, "the sudo variant is for non-root accounts")
    def test_sudo_variant(self):
        self.assertNotEqual(self.run_cmd("id -u").stdout.strip(), "0")
        (self.etc / "use-sudo").touch()
        result = self.run_cmd("id -u")
        if result.returncode == 0:
            self.assertEqual(result.stdout.strip(), "0")    # passwordless sudo ran it as root
        else:
            self.assertIn("sudo", result.stderr)            # sudo -n refused: no password prompt


FAKE_SUDO = """#!/bin/sh
# fake sudo: records its argv; "-n -l -- CMD..." allows only the commands listed in $ALLOW_FILE
printf '%s\\n' "$*" >> "$LOG_DIR/sudo.log"
if [ "$1" = -n ] && [ "$2" = -l ] && [ "$3" = -- ]; then
  shift 3
  grep -qxF -- "$*" "$ALLOW_FILE" && { echo "/usr/bin/$*"; exit 0; }
  exit 1
fi
[ "$1" = -n ] && [ "$2" = -- ] && { shift 2; exec "$@"; }
exit 99
"""

FAKE_LOGGER = """#!/bin/sh
# fake logger: one record per call, so a forged second line would show as a second record
printf '%s\\n' "$*" >> "$LOG_DIR/syslog"
"""


class InstalledDispatcherTest(unittest.TestCase):
    """The dispatcher as sshd runs it (no --etc, so it logs), with fake sudo and logger first on PATH."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        self.etc, self.bin, self.logs = base / "etc", base / "bin", base / "logs"
        for path in (self.etc, self.bin, self.logs):
            path.mkdir()
        (self.etc / "framework.allow").write_text(RULES)
        (self.etc / "local.allow").write_text("")
        for name, text in (("sudo", FAKE_SUDO), ("logger", FAKE_LOGGER)):
            (self.bin / name).write_text(text)
            (self.bin / name).chmod(0o755)
        (base / "sudo-allow").write_text("uname -r\nid -u\n")
        self.env = {"PATH": os.environ["PATH"], "LOG_DIR": str(self.logs), "ALLOW_FILE": str(base / "sudo-allow")}
        script = DISPATCHER.read_text()
        fixed = "export LC_ALL=C PATH=/usr/sbin:/usr/bin:/sbin:/bin"
        self.assertIn(fixed, script)
        self.assertIn("ETC=/etc/homelab-collect\n", script)
        script = script.replace(fixed, f"export LC_ALL=C PATH={self.bin}:/usr/sbin:/usr/bin:/sbin:/bin")
        script = script.replace("ETC=/etc/homelab-collect\n", f"ETC={self.etc}\n")
        self.dispatcher = base / "homelab-collect"
        self.dispatcher.write_text(script)

    def run_cmd(self, command: str):
        return subprocess.run(["bash", str(self.dispatcher)], env={**self.env, "SSH_ORIGINAL_COMMAND": command},
                              capture_output=True, text=True)

    def syslog(self) -> list:
        path = self.logs / "syslog"
        return path.read_text().splitlines() if path.exists() else []

    def test_a_newline_cannot_forge_a_second_log_line(self):
        result = self.run_cmd("pct config 101\nallowed: uname -r")
        self.assertEqual(result.returncode, 126)
        self.assertEqual(self.syslog(), ["-t homelab-collect -- refused: $'pct config 101\\nallowed: uname -r'"])

    def test_a_long_refused_command_is_truncated_in_the_log(self):
        self.run_cmd("y" * 4000)
        (line,) = self.syslog()
        self.assertEqual(line, "-t homelab-collect -- refused: " + "y" * 512)

    @unittest.skipIf(os.geteuid() == 0, "the sudo variant is for non-root accounts")
    def test_use_sudo_runs_only_what_sudo_allows(self):
        (self.etc / "use-sudo").touch()
        allowed = self.run_cmd("uname -r")
        self.assertEqual((allowed.returncode, allowed.stdout), (0, os.uname().release + "\n"), allowed.stderr)
        sudo_calls = (self.logs / "sudo.log").read_text().splitlines()
        self.assertEqual(sudo_calls, ["-n -l -- uname -r", "-n -- uname -r"])
        # allowed by the dispatcher, not by sudoers: refused distinctly, never run
        refused = self.run_cmd("pct config 101")
        self.assertEqual(refused.returncode, 126)
        self.assertEqual(refused.stderr, "homelab-collect: refused (sudo): pct config 101\n")
        self.assertEqual((self.logs / "sudo.log").read_text().splitlines()[-1], "-n -l -- pct config 101")
        self.assertIn("refused (sudo): pct config 101", self.syslog()[-1])


if __name__ == "__main__":
    unittest.main()
