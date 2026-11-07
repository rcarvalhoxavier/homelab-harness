import re
import unittest
from pathlib import Path

from tests import ROOT
from tests.toolkit import Lab
from wikitools.redact import env_values

LOAD = "source lib/pve/log.sh\nsource lib/pve/env.sh\nPVE_ROOT=$PWD\n"

PARITY_CASES = (
    "# a comment\n"
    "PLAIN=value\n"
    "SPACED = spaced value\n"
    "export EXPORTED=1\n"
    'DQ="double # not a comment"\n'
    "SQ='single $HOME `id` & x'\n"
    'UNCLOSED="unclosed\n'
    "COMMENT=abc # trailing\n"
    "HASH=abc#123\n"
    "EMPTY=\n"
    "TRAIL=value   \n"
    "CRLF=crlf\r\n"
    "TAB=a\t# tab comment\n"
    "=novar\n"
    "not an assignment\n"
)


class EnvParityTest(unittest.TestCase):
    def test_bash_parser_matches_the_python_one(self):
        lab = Lab()
        self.addCleanup(lab.close)
        lab.write_env(PARITY_CASES)
        result = lab.shell(LOAD + (
            'while IFS= read -r line || [[ -n "$line" ]]; do\n'
            '  if _pve_env_parse_line "$line"; then printf "%s=%s\\n" "$_PVE_ENV_KEY" "$_PVE_ENV_VAL"; fi\n'
            "done < .env.local\n"))
        self.assertEqual(result.returncode, 0, result.stderr)
        expected = "".join(f"{k}={v}\n" for k, v in env_values(lab.root / ".env.local").items())
        self.assertEqual(result.stdout, expected)


class EnvLoadTest(unittest.TestCase):
    def setUp(self):
        self.lab = Lab()
        self.addCleanup(self.lab.close)

    def load(self, text: str, show: str, **env):
        self.lab.write_env(text)
        return self.lab.shell(LOAD + "pve_env_load\n" + show, **env)

    def test_defaults(self):
        result = self.load("", 'echo "$PVE_STORAGE_WARN_PCT $PVE_BACKUP_MAX_AGE_DAYS '
                               '$HOMELAB_SSHPASS $HOMELAB_LOG [$PVE_BACKUP_STORAGE]"')
        self.assertEqual(result.stdout.strip(), "85 2 0 1 []")

    def test_a_relative_log_dir_is_under_the_repo(self):
        # from .env.local or from the environment, never against the working directory
        self.lab.write_env("HOMELAB_LOG_DIR=audit\n")
        result = self.lab.shell("unset HOMELAB_LOG_DIR\n" + LOAD + 'pve_env_load\ncd "$HOME" && echo "$HOMELAB_LOG_DIR"')
        self.assertEqual(result.stdout.strip(), f"{self.lab.root}/audit", result.stderr)
        result = self.load("", 'cd "$HOME" && echo "$HOMELAB_LOG_DIR"', HOMELAB_LOG_DIR="audit")
        self.assertEqual(result.stdout.strip(), f"{self.lab.root}/audit", result.stderr)
        result = self.load("", 'echo "$HOMELAB_LOG_DIR"', HOMELAB_LOG_DIR="/var/tmp/audit")
        self.assertEqual(result.stdout.strip(), "/var/tmp/audit")

    def test_known_names_load_and_unknown_names_are_ignored(self):
        result = self.load("PVE_BACKUP_STORAGE=nas-backup\nLD_PRELOAD=/tmp/evil.so\nNAS_HOST=nas.lan\n",
                           'echo "$PVE_BACKUP_STORAGE ${LD_PRELOAD-unset} ${NAS_HOST-unset}"')
        self.assertEqual(result.stdout.strip(), "nas-backup unset unset")
        self.assertNotIn("NAS_HOST", result.stderr)

    def test_the_environment_wins(self):
        result = self.load("PVE_STORAGE_WARN_PCT=90\n", 'echo "$PVE_STORAGE_WARN_PCT"',
                           PVE_STORAGE_WARN_PCT="70")
        self.assertEqual(result.stdout.strip(), "70")

    def test_invalid_values_are_configuration_errors(self):
        for line, name in (("PVE_STORAGE_WARN_PCT=abc", "PVE_STORAGE_WARN_PCT"),
                           ("PVE_STORAGE_WARN_PCT=0", "PVE_STORAGE_WARN_PCT"),
                           ("PVE_BACKUP_MAX_AGE_DAYS=-1", "PVE_BACKUP_MAX_AGE_DAYS"),
                           ("HOMELAB_SSHPASS=yes", "HOMELAB_SSHPASS"),
                           ("PVE_BACKUP_STORAGE=bad name", "PVE_BACKUP_STORAGE")):
            with self.subTest(line=line):
                result = self.load(line + "\n", "true")
                self.assertEqual(result.returncode, 2)
                self.assertIn(name, result.stderr)

    def test_password_is_literal_and_never_exported(self):
        secret = "p$ss`w&rd#1 x"
        result = self.load(f"HOMELAB_SSHPASS=1\r\nSSHPASS='{secret}'\r\n",
                           'printf "%s|" "$_PVE_SSHPASS"; '
                           'if env | grep -q "^SSHPASS="; then echo exported; else echo private; fi')
        self.assertEqual(result.stdout, f"{secret}|private\n")

    def test_password_unquoted_with_hash(self):
        result = self.load("HOMELAB_SSHPASS=1\nSSHPASS=abc#123\n", 'printf "%s" "$_PVE_SSHPASS"')
        self.assertEqual(result.stdout, "abc#123")

    def test_fallback_without_password_is_an_error(self):
        result = self.load("HOMELAB_SSHPASS=1\n", "true")
        self.assertEqual(result.returncode, 2)
        self.assertIn("SSHPASS", result.stderr)

    def test_example_documents_only_known_names(self):
        known = self.lab.shell(LOAD + 'printf "%s\\n" "${PVE_ENV_NAMES[@]}"').stdout.split()
        names = re.findall(r"^#?\s*([A-Z_]+)=", (ROOT / ".env.local.example").read_text(), re.M)
        self.assertTrue(names)
        self.assertLessEqual(set(names), set(known))


class AuditTest(unittest.TestCase):
    def test_audit_log_has_header_lines_and_exit(self):
        lab = Lab()
        self.addCleanup(lab.close)
        result = lab.shell(LOAD + "pve_env_load\npve_audit_start demo --flag\n"
                                  "log_info hello\nexit 3\n")
        self.assertEqual(result.returncode, 3)
        text = lab.audit_text()
        for expected in ("tool: demo", "args: --flag", "[INFO] hello", "finished: exit 3"):
            self.assertIn(expected, text)

    def test_cleanup_paths_are_removed_at_exit(self):
        lab = Lab()
        self.addCleanup(lab.close)
        result = lab.shell(LOAD + 'd="$(mktemp -d)"; pve_cleanup_add "$d"; echo "$d"')
        self.assertFalse(Path(result.stdout.strip()).exists())


if __name__ == "__main__":
    unittest.main()
