import subprocess
import unittest

from tests.toolkit import Lab


class FakeSshTest(unittest.TestCase):
    def setUp(self):
        self.lab = Lab(restricted=False)
        self.addCleanup(self.lab.close)

    def call(self, *argv, **env):
        self.lab.save()
        return subprocess.run(list(argv), env=self.lab.env(**env), capture_output=True, text=True)

    def test_answers_a_known_command_and_records_it(self):
        self.lab.respond("pve1", "pct list", stdout="VMID Status\n")
        result = self.call("ssh", "-n", "-o", "BatchMode=yes", "--", "pve1", "pct list")
        self.assertEqual((result.returncode, result.stdout), (0, "VMID Status\n"))
        call = self.lab.calls()[0]
        self.assertEqual((call["alias"], call["role"], call["node"], call["command"]),
                         ("pve1", "collect", "pve1", "pct list"))
        self.assertIn("-o BatchMode=yes", call["options"])
        self.assertIn("-n", call["options"])

    def test_unknown_command_is_recorded_as_unexpected(self):
        result = self.call("ssh", "pve1", "qm list")
        self.assertEqual(result.returncode, 127)
        self.assertTrue(self.lab.calls()[0]["unexpected"])

    def test_unreachable_alias_exits_255(self):
        self.lab.unreachable("pve1")
        result = self.call("ssh", "pve1", "uname -r")
        self.assertEqual(result.returncode, 255)
        self.assertIn("No route to host", result.stderr)

    def test_admin_command_goes_through_a_real_bash(self):
        self.lab.respond("pve1", "printf %s a b;c", stdout="ok")
        result = self.call("ssh", "pve1-admin", "printf %s 'a b;c'")
        self.assertEqual(result.stdout, "ok")
        self.assertEqual(self.lab.calls()[0]["argv"], ["printf", "%s", "a b;c"])

    def test_sequences_and_regex_keys(self):
        self.lab.respond_seq("pve1", "pct status 101",
                             {"stdout": "status: stopped\n"}, {"stdout": "status: running\n"})
        self.lab.respond("pve1", r"re:pct snapshot 101 pre-update-\d{8}-\d{4}")
        outputs = [self.call("ssh", "pve1", "pct status 101").stdout for _ in range(3)]
        self.assertEqual(outputs, ["status: stopped\n", "status: running\n", "status: running\n"])
        self.assertEqual(self.call("ssh", "pve1-admin", "pct snapshot 101 pre-update-20261014-0930")
                         .returncode, 0)

    def test_scp_records_the_content(self):
        source = self.lab.base / "file.txt"
        source.write_text("hello\n")
        result = self.call("scp", "-o", "BatchMode=yes", "-q", "--", str(source), "pve1-admin:/tmp/x")
        self.assertEqual(result.returncode, 0)
        call = self.lab.calls("scp")[0]
        self.assertEqual((call["alias"], call["path"], call["content"]), ("pve1-admin", "/tmp/x", "hello\n"))

    def test_sshpass_accepts_only_dash_e(self):
        self.lab.respond("pve1", "uname -r", stdout="6.8.12-10-pve\n")
        refused = self.call("sshpass", "-p", "secret", "ssh", "pve1", "uname -r")
        self.assertEqual(refused.returncode, 99)
        self.assertEqual(self.lab.calls("sshpass")[0]["misuse"], ["-p", "secret"])
        accepted = self.call("sshpass", "-e", "ssh", "pve1", "uname -r", SSHPASS="secret")
        self.assertEqual(accepted.stdout, "6.8.12-10-pve\n")
        self.assertTrue(self.lab.calls()[0]["sshpass"])


class FakeSshRestrictedTest(unittest.TestCase):
    def setUp(self):
        self.lab = Lab(restricted=True)
        self.addCleanup(self.lab.close)

    def call(self, command):
        self.lab.save()
        return subprocess.run(["ssh", "pve1", command], env=self.lab.env(),
                              capture_output=True, text=True)

    def test_dispatcher_refuses_a_command_outside_the_lists(self):
        result = self.call("rm -rf /")
        self.assertEqual(result.returncode, 126)
        self.assertIn("homelab-collect: refused: rm -rf /", result.stderr)
        self.assertTrue(self.lab.calls()[0]["refused"])

    def test_dispatcher_lets_an_allowed_command_reach_the_scenario(self):
        self.lab.respond("pve1", "uname -r", stdout="6.8.12-pve\n")
        result = self.call("uname -r")
        self.assertEqual((result.returncode, result.stdout), (0, "6.8.12-pve\n"))
        self.assertFalse(self.lab.calls()[0]["refused"])

    def test_local_allow_extends_the_framework_list(self):
        self.lab.install_lists(local="pct exec 101 -- pihole -v\n")
        self.lab.respond("pve1", "pct exec 101 -- pihole -v", stdout="v6\n")
        self.assertEqual(self.call("pct exec 101 -- pihole -v").returncode, 0)
        self.assertEqual(self.call("pct exec 102 -- pihole -v").returncode, 126)


if __name__ == "__main__":
    unittest.main()
