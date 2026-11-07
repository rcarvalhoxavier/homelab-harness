"""Layer 2: the toolkit against a real sshd on localhost. CI only: tests/sshd/setup.sh prepares it."""
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from tests import ROOT

SSHD_DIR = Path("/tmp/harness-sshd")


@unittest.skipUnless(os.environ.get("HARNESS_SSHD_TEST") == "1",
                     "needs the sshd prepared by tests/sshd/setup.sh (CI job 'sshd')")
class RealSshdTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls._tmp.name) / "repo"
        for part in ("bin", "lib", "remote"):
            shutil.copytree(ROOT / part, cls.root / part)
        (cls.root / "inventory").mkdir()

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def bash(self, script: str, inventory: str = "ci ci ci-admin\n", env_file: str = ""):
        (self.root / "inventory" / "nodes").write_text(inventory)
        (self.root / ".env.local").write_text(env_file)
        return subprocess.run(["bash", "-c", "set -euo pipefail\nsource lib/pve/init.sh\npve_env_load\n"
                                             "pve_inventory_load\n" + script],
                              cwd=self.root, env={**os.environ, "HOMELAB_LOG": "0"},
                              capture_output=True, text=True, timeout=60)

    def test_the_collect_key_runs_an_allowed_command(self):
        result = self.bash("pve_collect ci pct list")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("pihole", result.stdout)

    def test_the_collect_key_runs_the_pvesm_stub(self):
        result = self.bash("pve_collect ci pvesm status")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("local", result.stdout)
        self.assertIn("active", result.stdout)

    def test_the_collect_key_refuses_everything_else(self):
        result = self.bash("pve_collect ci id")
        self.assertEqual(result.returncode, 126)
        self.assertIn("refused by the host's dispatcher", result.stderr)

    def test_sshd_hands_chaining_and_shells_to_the_dispatcher(self):
        for remote in (["pct list; id"], ["pct list && id"], ["pct", "list", "&&", "id"], []):
            with self.subTest(remote=remote):
                result = subprocess.run(["ssh", "-n", "-o", "BatchMode=yes", "ci", *remote],
                                        capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 126)
                self.assertIn("homelab-collect: refused", result.stderr)

    def test_the_dispatcher_version_matches_the_repo(self):
        result = self.bash("pve_collect ci homelab-collect --version\npve_collect_hash")
        self.assertEqual(result.returncode, 0, result.stderr)
        reported, expected = result.stdout.splitlines()
        self.assertEqual(reported, f"homelab-collect {expected}")

    def test_admin_quoting_survives_the_real_remote_shell(self):
        result = self.bash("pve_admin ci printf '%s|' 'a b' '$HOME' ';' \"it's\" '*'")
        self.assertEqual(result.stdout, "a b|$HOME|;|it's|*|")

    def test_batch_mode_fails_fast_without_a_key(self):
        start = time.monotonic()
        result = self.bash("pve_collect ci uname -r", inventory="ci ci-nokey ci-admin\n")
        self.assertEqual(result.returncode, 255)
        self.assertLess(time.monotonic() - start, 15)

    def test_password_fallback_works_and_has_no_forced_command(self):
        password = (SSHD_DIR / "password").read_text().strip()
        env_file = f"HOMELAB_SSHPASS=1\nSSHPASS={password}\n"
        result = self.bash("pve_collect ci uname -r", inventory="ci ci-pw ci-pw2\n", env_file=env_file)
        self.assertEqual(result.returncode, 0, result.stderr)
        unrestricted = self.bash("pve_collect ci id", inventory="ci ci-pw ci-pw2\n", env_file=env_file)
        self.assertEqual(unrestricted.returncode, 0)   # why pve-selftest warns about the fallback
        for text in (result.stdout, result.stderr, unrestricted.stdout, unrestricted.stderr):
            self.assertNotIn(password, text)


if __name__ == "__main__":
    unittest.main()
