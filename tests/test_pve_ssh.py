import re
import shutil
import unittest
from pathlib import Path

from tests.toolkit import Lab

LOAD = "pve_env_load\npve_inventory_load\n"


class CollectTest(unittest.TestCase):
    def setUp(self):
        self.lab = Lab()
        self.addCleanup(self.lab.close)

    def test_sends_the_argv_as_one_string_with_fixed_options(self):
        self.lab.respond("pve1", "pct config 101", stdout="arch: amd64\n")
        result = self.lab.bash(LOAD + "pve_collect pve1 pct config 101")
        self.assertEqual(result.stdout, "arch: amd64\n")
        call = self.lab.calls()[0]
        self.assertEqual((call["alias"], call["command"], call["sshpass"]), ("pve1", "pct config 101", False))
        for option in ("-n", "-o BatchMode=yes", "-o ConnectTimeout=10",
                       "-o ServerAliveInterval=15", "-o ServerAliveCountMax=3"):
            self.assertIn(option, call["options"])

    def test_rejects_shell_syntax_before_connecting(self):
        for bad in ("'/etc/x; id'", "'a b'", "'$(id)'", "''"):
            with self.subTest(bad=bad):
                result = self.lab.bash(LOAD + f"pve_collect pve1 cat {bad}")
                self.assertEqual(result.returncode, 2)
        self.assertEqual(self.lab.calls(), [])

    def test_dispatcher_refusal_is_reported_clearly(self):
        result = self.lab.bash(LOAD + "pve_collect pve1 id")
        self.assertEqual(result.returncode, 126)
        self.assertIn("refused by the host's dispatcher on pve1: 'id'", result.stderr)

    def test_a_sudo_refusal_is_reported_as_such(self):
        self.lab.respond("pve1", "pct list", exit=126, stderr="homelab-collect: refused (sudo): pct list\n")
        result = self.lab.bash(LOAD + "pve_collect pve1 pct list")
        self.assertEqual(result.returncode, 126)
        self.assertIn("refused by sudo on pve1: 'pct list': every command of the allowlists must be allowed "
                      "in sudoers (docs/ssh-access.md §7)", result.stderr)

    def test_unreachable_node(self):
        self.lab.unreachable("pve1")
        result = self.lab.bash(LOAD + "if pve_reachable pve1; then echo up; else echo down; fi\n"
                                      "pve_collect pve1 uname -r")
        self.assertEqual((result.stdout, result.returncode), ("down\n", 255))

    def test_every_call_disables_connection_sharing(self):
        # pve1 and pve1-admin reach the same root@host:22; a shared ControlMaster socket would run
        # reads through the admin key or changes through the restricted one
        source = self.lab.base / "demo.conf"
        source.write_text("x\n")
        self.lab.respond("pve1", "uname -r", stdout="6.8.12-10-pve\n")
        self.lab.respond("pve1", "true")
        self.lab.respond("pve1", "mktemp /tmp/homelab-put.XXXXXXXX", stdout="/tmp/homelab-put.Ab3dE5gH\n")
        self.lab.respond("pve1", "re:(install|rm) .*")
        result = self.lab.bash(LOAD + f"pve_collect pve1 uname -r\npve_admin pve1 true\n"
                                      f"pve_admin_put pve1 {source} /etc/demo.conf 0644")
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.lab.calls() + self.lab.calls("scp")
        self.assertEqual({call["role"] for call in calls}, {"collect", "admin"})
        self.assertIn("scp", {call["tool"] for call in calls})
        for call in calls:
            options = call["options"]
            if call["tool"] == "scp":
                options = [f"{a} {b}" for a, b in zip(options, options[1:]) if a == "-o"]
            self.assertIn("-o ControlMaster=no", options, call)
            self.assertIn("-o ControlPath=none", options, call)

    def test_audit_log_is_private(self):
        logs = self.lab.base / "logs"
        result = self.lab.bash(LOAD + "pve_audit_start demo\nlog_info hello")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(logs.stat().st_mode & 0o777, 0o700)
        files = list(logs.glob("*.log"))
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].stat().st_mode & 0o777, 0o600)

    def test_audit_records_each_command(self):
        self.lab.respond("pve1", "uname -r", stdout="6.8.12-10-pve\n")
        self.lab.bash(LOAD + "pve_audit_start demo\npve_collect pve1 uname -r")
        self.assertIn("collect pve1 (pve1): uname -r -> exit 0", self.lab.audit_text())


class AdminTest(unittest.TestCase):
    def setUp(self):
        self.lab = Lab()
        self.addCleanup(self.lab.close)

    def test_quoting_round_trip(self):
        argv = ["printf", "%s|", "a b", "$HOME", ";", "it's", "x\ny", "*"]
        self.lab.respond("pve1", " ".join(argv), stdout="ok")
        result = self.lab.bash(LOAD + "pve_admin pve1 printf '%s|' 'a b' '$HOME' ';' \"it's\" $'x\\ny' '*'")
        self.assertEqual(result.stdout, "ok", result.stderr)
        call = self.lab.calls()[0]
        self.assertEqual((call["alias"], call["role"], call["argv"]), ("pve1-admin", "admin", argv))

    def test_put_copies_then_installs_then_cleans(self):
        source = self.lab.base / "demo.conf"
        source.write_text("key = value\n")
        tmp = "/tmp/homelab-put.Ab3dE5gH"
        self.lab.respond("pve1", "mktemp /tmp/homelab-put.XXXXXXXX", stdout=tmp + "\n")
        self.lab.respond("pve1", f"install -o root -g root -m 0644 {tmp} /etc/demo.conf")
        self.lab.respond("pve1", f"rm -f {tmp}")
        result = self.lab.bash(LOAD + f"pve_admin_put pve1 {source} /etc/demo.conf 0644")
        self.assertEqual(result.returncode, 0, result.stderr)
        copy = self.lab.calls("scp")[0]
        self.assertEqual((copy["alias"], copy["content"], copy["path"]), ("pve1-admin", "key = value\n", tmp))
        # the remote temporary file is created by mktemp on the host, never a predictable name
        self.assertEqual(self.lab.commands("admin"), ["mktemp /tmp/homelab-put.XXXXXXXX",
                                                      f"install -o root -g root -m 0644 {tmp} /etc/demo.conf",
                                                      f"rm -f {tmp}"])

    def test_put_stops_when_mktemp_does_not_answer_a_path(self):
        for answer in ({"stdout": ""}, {"stdout": "/tmp/x; id\n"}, {"exit": 1, "stderr": "mktemp: failed\n"}):
            with self.subTest(answer=answer):
                self.lab.respond("pve1", "mktemp /tmp/homelab-put.XXXXXXXX", **answer)
                result = self.lab.bash(LOAD + "pve_admin_put pve1 /etc/hosts /etc/x 0644")
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.lab.calls("scp"), [])
                self.assertFalse([c for c in self.lab.commands("admin") if not c.startswith("mktemp ")])

    def test_put_rejects_a_bad_mode_or_a_relative_destination(self):
        for call in ("pve_admin_put pve1 /etc/hosts /etc/x 644", "pve_admin_put pve1 /etc/hosts etc/x 0644"):
            with self.subTest(call=call):
                result = self.lab.bash(LOAD + call)
                self.assertEqual(result.returncode, 2)
        self.assertEqual(self.lab.calls(), [])


class FallbackTest(unittest.TestCase):
    SECRET = "s3cr3t-Pa$$w0rd"

    def test_password_goes_only_to_sshpass_e(self):
        lab = Lab()
        self.addCleanup(lab.close)
        lab.write_env(f"HOMELAB_SSHPASS=1\nSSHPASS={self.SECRET}\n")
        lab.respond("pve1", "uname -r", stdout="6.8.12-10-pve\n")
        lab.respond("pve1", "true")
        result = lab.bash(LOAD + "pve_audit_start demo\npve_collect pve1 uname -r\npve_admin pve1 true")
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = lab.calls()
        self.assertEqual(len(calls), 2)
        for call in calls:
            self.assertTrue(call["sshpass"])
            self.assertIn("-o BatchMode=no", call["options"])
            self.assertIn("-o PubkeyAuthentication=no", call["options"])
            self.assertNotIn("-o BatchMode=yes", call["options"])
        self.assertEqual(lab.calls("sshpass"), [])
        for text in (lab.log.read_text(), result.stdout, result.stderr, lab.audit_text()):
            self.assertNotIn(self.SECRET, text)

    def test_missing_sshpass_is_reported_on_every_entry_point(self):
        lab = Lab()
        self.addCleanup(lab.close)
        lab.write_env("HOMELAB_SSHPASS=1\nSSHPASS=x\n")
        tools = lab.base / "tools"
        tools.mkdir()
        for name in ("bash", "mktemp", "grep", "cat", "rm", "dirname", "sed", "awk", "date",
                     "uname", "env", "tr", "sort", "id", "hostname", "mkdir", "tee"):
            found = shutil.which(name)
            if found:
                (tools / name).symlink_to(found)
        for call in ("pve_collect pve1 uname -r", "pve_admin pve1 true", "pve_reachable pve1",
                     "pve_admin_put pve1 /etc/hosts /etc/x 0644"):
            with self.subTest(call=call):
                result = lab.bash(LOAD + call, PATH=str(tools))
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("needs sshpass", result.stderr)
        self.assertEqual(lab.calls(), [])


if __name__ == "__main__":
    unittest.main()
