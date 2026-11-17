import unittest

from tests import pvefixtures as fx
from tests.toolkit import Lab

LOAD = "pve_init demo\n"


class SshLocaleTest(unittest.TestCase):
    """The ssh calls ask the host for the C locale; a dispatcher that fixes it makes this a no-op."""

    def setUp(self):
        self.lab = Lab()
        self.addCleanup(self.lab.close)
        self.lab.respond("pve1", "uname -r", stdout="6.8.12-10-pve\n")
        self.lab.respond("pve1", "true")

    def assert_c_locale(self, call):
        self.assertIn("-o SendEnv=LC_ALL", call["options"], call)
        # the test environment sets LC_ALL=C.UTF-8; the call must override it
        self.assertEqual(call["lc_all"], "C", call)

    def test_collect_and_admin_calls_send_the_c_locale(self):
        result = self.lab.bash(LOAD + "pve_collect pve1 uname -r\npve_admin pve1 true")
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.lab.calls()
        self.assertEqual([call["role"] for call in calls], ["collect", "admin"])
        for call in calls:
            self.assert_c_locale(call)

    def test_the_remote_command_line_is_unchanged(self):
        self.lab.bash(LOAD + "pve_collect pve1 uname -r")
        self.assertEqual(self.lab.calls()[0]["command"], "uname -r")

    def test_the_password_fallback_sends_it_too(self):
        result = self.lab.bash(LOAD + "pve_collect pve1 uname -r", HOMELAB_SSHPASS=1, SSHPASS="x")
        self.assertEqual(result.returncode, 0, result.stderr)
        for call in self.lab.calls():
            self.assert_c_locale(call)


class ParserHintTest(unittest.TestCase):
    def setUp(self):
        self.lab = Lab()
        self.addCleanup(self.lab.close)
        fx.load(self.lab)

    def test_health_names_a_non_english_locale_when_free_has_no_mem_line(self):
        # free in German: the "Mem:" row is "Speicher:"
        self.lab.respond("pve1", "free -b", stdout="  gesamt benutzt frei\nSpeicher: 33 11 22\nSwap: 0 0 0\n")
        result = self.lab.run("pve-health", "--today", "2026-07-01", "--node", "pve1")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("finding CRIT could not read memory on pve1\n", result.stdout)
        self.assertIn("a non-English locale on the host is a possible cause", result.stderr)

    def test_a_good_free_answer_has_no_hint(self):
        result = self.lab.run("pve-health", "--today", "2026-07-01", "--node", "pve1")
        self.assertNotIn("locale", result.stderr)


if __name__ == "__main__":
    unittest.main()
