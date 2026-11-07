import io
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from tests.helpers import GIT_ENV, append, clean_wiki, codes, copy_harness, lint, run_bin, write_files
from wikitools import init

JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0In0.c2lnbmF0dXJlX2hlcmU"


class LintSecretsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.wiki = clean_wiki(self.base)

    def tearDown(self):
        self.tmp.cleanup()

    def test_secret_in_raw(self):
        write_files(self.wiki, {"raw/2026-06-02-leak.txt": "password=hunter22\n"})
        self.assertIn(("E-SECRET", "raw/2026-06-02-leak.txt"), codes(lint(self.wiki)))

    def test_key_value_only_flagged_in_code(self):
        append(self.wiki / "overview.md", "\nThe token: rotate it yearly.\n")
        self.assertEqual(lint(self.wiki), [])
        append(self.wiki / "overview.md", "\n```\ntoken: abcdef123456\n```\n")
        found = lint(self.wiki)
        self.assertEqual(codes(found), [("E-SECRET", "overview.md")])
        self.assertEqual(found[0].line, 8)

    def test_high_precision_rules_scan_prose(self):
        append(self.wiki / "overview.md", f"\nLeaked {JWT} here.\n")
        self.assertEqual(codes(lint(self.wiki)), [("E-SECRET", "overview.md")])

    def test_redaction_markers_are_fine(self):
        append(self.wiki / "overview.md",
               "\n```\npassword: <REDACTED:secret>\nhttps://u:<REDACTED:password>@h/x\n```\n")
        self.assertEqual(lint(self.wiki), [])

    def test_env_literal_in_page(self):
        env = self.base / ".env.local"
        env.write_text("PVE_ROOT_PASSWORD=Tr0ub4dor&3\n")
        append(self.wiki / "overview.md", "\nThe old one was Tr0ub4dor&3.\n")
        self.assertEqual(codes(lint(self.wiki, env_file=env)), [("E-SECRET", "overview.md")])

    def test_exposure(self):
        public = clean_wiki(self.base / "pub", exposure="public")
        self.assertEqual(lint(public), [])
        append(public / "overview.md", "\ncontroller_version: 6.3.0.45\n")
        self.assertEqual(lint(public), [])
        append(public / "overview.md", "\nGateway 10.0.0.1.\n")
        self.assertEqual(codes(lint(public)), [("E-EXPOSURE", "overview.md")])
        append(self.wiki / "overview.md", "\nGateway 10.0.0.1.\n")
        self.assertEqual(lint(self.wiki), [])

    def test_only_secrets_with_paths(self):
        write_files(self.wiki, {"concepts/orphan.md": "# Orphan\n"})
        dirty = self.wiki / "concepts" / "dirty.md"
        dirty.write_text(f"# Dirty\n\n{JWT}\n")
        clean = self.wiki / "entities" / "host-pve1.md"
        result = run_bin("wiki-lint", "--wiki", self.wiki, "--env-file", self.base / "none",
                         "--only", "secrets", "--paths", dirty, clean)
        self.assertEqual(result.returncode, 1)
        self.assertIn("E-SECRET", result.stdout)
        self.assertNotIn("W-ORPHAN", result.stdout)
        result = run_bin("wiki-lint", "--wiki", self.wiki, "--env-file", self.base / "none",
                         "--only", "secrets", "--paths", clean)
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_paths_requires_only_secrets(self):
        result = run_bin("wiki-lint", "--wiki", self.wiki, "--paths", self.wiki / "index.md")
        self.assertEqual(result.returncode, 2)


class EndToEndTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = copy_harness(Path(self.tmp.name))
        patcher = mock.patch.dict(os.environ, GIT_ENV)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def init(self, *args):
        with redirect_stdout(io.StringIO()):
            return init.main(["--root", str(self.root), "--non-interactive", *args])

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), "-c", "user.name=t",
                               "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false", *args],
                              capture_output=True, text=True)

    def test_fresh_init_lints_clean(self):
        self.init()
        self.assertEqual(lint(self.root / "wiki"), [])

    def test_capture_then_lint_shows_only_the_ingest_todo(self):
        self.init()
        wiki = self.root / "wiki"
        result = subprocess.run([str(self.root / "bin" / "wiki-capture"), "pve1-versions",
                                 "--date", "2026-06-01", "--wiki", str(wiki),
                                 "--env-file", str(self.root / "none")],
                                input="pve-manager/8.4.1\n", capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        source = "sources/2026-06-01-pve1-versions.md"
        self.assertEqual(set(codes(lint(wiki))),
                         {("W-STUB", source), ("W-ORPHAN", source), ("W-INDEX", source)})

    def test_pre_commit_hook_blocks_staged_secrets(self):
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        self.assertEqual(self.init("--hooks"), 0)
        self.git("add", "-A")
        self.assertEqual(self.git("commit", "-qm", "init").returncode, 0)
        overview = self.root / "wiki" / "overview.md"
        append(overview, f"\nLeaked {JWT}\n")
        self.git("add", "wiki/overview.md")
        blocked = self.git("commit", "-qm", "leak")
        self.assertNotEqual(blocked.returncode, 0)
        self.assertIn("E-SECRET", blocked.stdout + blocked.stderr)
        overview.write_text(overview.read_text().replace(JWT, "a token (rotated)"))
        self.git("add", "wiki/overview.md")
        self.assertEqual(self.git("commit", "-qm", "fixed").returncode, 0)


class SecretRegressionTest(unittest.TestCase):
    """Secrets the lint once missed."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.wiki = clean_wiki(self.base)

    def tearDown(self):
        self.tmp.cleanup()

    def test_secret_looking_values_in_prose_lists_and_tables(self):
        append(self.wiki / "overview.md",
               "\nAdmin UI login: admin / password: Hunter2Hunter2\n\n"
               "- Web password: Sup3rS3cret!\n- API token: 7f3a9c2e81d4b6a0\n\n"
               "| Field | Value |\n|---|---|\n| password | CorrectHorse99 |\n")
        found = [(f.code, f.line) for f in lint(self.wiki)]
        self.assertEqual(found, [("E-SECRET", 5), ("E-SECRET", 7), ("E-SECRET", 8), ("E-SECRET", 12)])

    def test_ordinary_prose_about_secrets_is_fine(self):
        append(self.wiki / "overview.md",
               "\nThe API token: stored in the vault.\n\n"
               "| Setting | Meaning |\n|---|---|\n| token | the API token of the NAS |\n")
        self.assertEqual(lint(self.wiki), [])

    def test_exposure_message_explains_versions(self):
        public = clean_wiki(self.base / "pub", exposure="public")
        append(public / "overview.md", "\nUpgraded from 5.15.20.20 to 5.15.24.18.\n")
        found = lint(public)
        self.assertEqual({f.code for f in found}, {"E-EXPOSURE"})
        self.assertIn("v6.3.0.45", found[0].message)

    def test_only_secrets_rejects_missing_paths(self):
        result = run_bin("wiki-lint", "--wiki", self.wiki, "--only", "secrets",
                         "--paths", self.wiki / "nope.md")
        self.assertEqual(result.returncode, 2)
        self.assertIn("nope.md", result.stderr)


class HookBypassTest(unittest.TestCase):
    """The pre-commit hook scans the staged copy of added, modified and renamed files."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = copy_harness(Path(self.tmp.name))
        patcher = mock.patch.dict(os.environ, GIT_ENV)
        patcher.start()
        self.addCleanup(patcher.stop)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        with redirect_stdout(io.StringIO()):
            init.main(["--root", str(self.root), "--non-interactive", "--hooks"])
        # Long enough that a small edit keeps git's rename similarity high (status R09x).
        body = "".join(f"Line {n} of a long, harmless page.\n" for n in range(40))
        write_files(self.root / "wiki", {"concepts/foo.md": "# Foo\n\n" + body})
        self.git("add", "-A")
        self.assertEqual(self.git("commit", "-qm", "init").returncode, 0)

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), "-c", "user.name=t",
                               "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false", *args],
                              capture_output=True, text=True)

    def assert_blocked(self):
        result = self.git("commit", "-qm", "leak")
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("E-SECRET", result.stdout + result.stderr)

    def test_renamed_file(self):
        self.git("mv", "wiki/concepts/foo.md", "wiki/concepts/bar.md")
        append(self.root / "wiki" / "concepts" / "bar.md", f"\n{JWT}\n")
        self.git("add", "-A")
        status = self.git("diff", "--cached", "--name-status").stdout
        self.assertRegex(status, r"(?m)^R\d+", "the edit must still be seen as a rename")
        self.assert_blocked()

    def test_non_ascii_file_name(self):
        write_files(self.root / "wiki", {"concepts/configuração.md": f"# Config\n\n{JWT}\n"})
        self.git("add", "-A")
        self.assert_blocked()

    def test_staged_copy_is_scanned_not_the_working_tree(self):
        overview = self.root / "wiki" / "overview.md"
        clean_text = overview.read_text()
        append(overview, f"\nLeaked {JWT}\n")
        self.git("add", "wiki/overview.md")
        overview.write_text(clean_text)
        self.assert_blocked()


if __name__ == "__main__":
    unittest.main()


def allow_entry(path: str, line: str, rule: str, reason: str = "reviewed: not a secret") -> str:
    from wikitools.util import short_hash
    return f"{path} {short_hash(line.encode())} {rule}  # {reason}\n"


class AllowTest(unittest.TestCase):
    """wiki/.secret-scan-allow: reviewed false positives of the secret scan, one line each."""

    LEAK = "raw/2026-06-02-leak.txt"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.wiki = clean_wiki(self.base)
        write_files(self.wiki, {self.LEAK: "first line\npassword=hunter22\n"})

    def tearDown(self):
        self.tmp.cleanup()

    def allow(self, *entries: str):
        (self.wiki / ".secret-scan-allow").write_text("# reviewed exceptions\n\n" + "".join(entries))

    def found(self, wiki=None):
        """Findings except W-RAW-UNCITED: the test raw files have no source page."""
        return [f for f in lint(wiki or self.wiki) if f.code != "W-RAW-UNCITED"]

    def linter(self):
        import datetime
        from wikitools.lint import Linter
        linter = Linter(self.wiki, datetime.date(2026, 7, 1))
        linter.run()
        return linter

    def test_an_allowed_line_is_not_reported(self):
        self.allow(allow_entry(f"wiki/{self.LEAK}", "password=hunter22", "key-value"))
        linter = self.linter()
        self.assertEqual([f for f in linter.sorted_findings() if f.code != "W-RAW-UNCITED"], [])
        self.assertEqual(linter.allowed, 1)

    def test_an_entry_survives_a_moved_line(self):
        self.allow(allow_entry(f"wiki/{self.LEAK}", "password=hunter22", "key-value"))
        (self.wiki / self.LEAK).write_text("new first line\nfirst line\npassword=hunter22\n")
        self.assertEqual(self.found(), [])

    def test_a_changed_line_is_reported_again(self):
        self.allow(allow_entry(f"wiki/{self.LEAK}", "password=hunter22", "key-value"))
        (self.wiki / self.LEAK).write_text("first line\npassword=hunter23\n")
        self.assertEqual(set(codes(self.found())),
                         {("E-SECRET", self.LEAK), ("W-ALLOW-STALE", ".secret-scan-allow")})

    def test_an_entry_allows_only_its_rule(self):
        line = "K=http://h:8080/?token=ABCdef123456"
        write_files(self.wiki, {self.LEAK: line + "\n"})
        self.allow(allow_entry(f"wiki/{self.LEAK}", line, "key-value"))
        found = self.found()
        self.assertEqual(codes(found), [("E-SECRET", self.LEAK)])
        self.assertIn("query-parameter", found[0].message)

    def test_an_entry_for_another_file_does_not_apply(self):
        self.allow(allow_entry("wiki/raw/other.txt", "password=hunter22", "key-value"))
        self.assertIn(("E-SECRET", self.LEAK), codes(self.found()))

    def test_an_entropy_warning_can_be_allowed(self):
        write_files(self.wiki, {self.LEAK: "session = Zq8vR2mN5pL1xC7bW4kT\n"})
        self.assertEqual(codes(self.found()), [("W-ENTROPY", self.LEAK)])
        self.allow(allow_entry(f"wiki/{self.LEAK}", "session = Zq8vR2mN5pL1xC7bW4kT", "entropy"))
        self.assertEqual(self.found(), [])

    def test_an_exposure_finding_cannot_be_allowed(self):
        public = clean_wiki(self.base / "pub", exposure="public")
        write_files(public, {"raw/net.txt": "gateway 10.0.0.1\n",
                             ".secret-scan-allow": allow_entry("wiki/raw/net.txt", "gateway 10.0.0.1", "ipv4")})
        self.assertIn(("E-EXPOSURE", "raw/net.txt"), codes(self.found(public)))

    def test_an_entry_without_a_reason_is_a_config_error(self):
        self.allow(allow_entry(f"wiki/{self.LEAK}", "password=hunter22", "key-value", reason=""))
        found = self.found()
        self.assertIn(("E-CONFIG", ".secret-scan-allow"), codes(found))
        self.assertIn(("E-SECRET", self.LEAK), codes(found))
        self.assertEqual([f.line for f in found if f.code == "E-CONFIG"], [3])

    def test_a_malformed_entry_is_a_config_error(self):
        self.allow(f"wiki/{self.LEAK} nothex key-value  # reason\n")
        self.assertIn(("E-CONFIG", ".secret-scan-allow"), codes(self.found()))

    def test_an_entry_matching_no_line_is_stale(self):
        self.allow(allow_entry(f"wiki/{self.LEAK}", "password=hunter22", "key-value"),
                   allow_entry("wiki/raw/gone.txt", "x", "key-value"))
        found = self.found()
        self.assertEqual(codes(found), [("W-ALLOW-STALE", ".secret-scan-allow")])
        self.assertEqual(found[0].line, 4)
        self.assertIn("wiki/raw/gone.txt", found[0].message)

    def test_print_allow_writes_candidate_entries(self):
        result = run_bin("wiki-lint", "--wiki", self.wiki, "--env-file", self.base / "none",
                         "--only", "secrets", "--print-allow")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout,
                         allow_entry(f"wiki/{self.LEAK}", "password=hunter22", "key-value", reason=""))
        entry = result.stdout.rstrip("\n") + "PASS counter of a test log\n"
        (self.wiki / ".secret-scan-allow").write_text(entry)
        result = run_bin("wiki-lint", "--wiki", self.wiki, "--env-file", self.base / "none",
                         "--only", "secrets")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("wiki-lint: 0 error(s), 0 warning(s), 0 info, 1 allowed", result.stdout)

    def test_print_allow_requires_only_secrets(self):
        result = run_bin("wiki-lint", "--wiki", self.wiki, "--print-allow")
        self.assertEqual(result.returncode, 2)

    def test_paths_root_maps_staged_copies_to_repository_paths(self):
        staged = self.base / "staged"
        write_files(staged, {f"wiki/{self.LEAK}": "password=hunter22\n",
                             "local/notes.txt": "password=hunter22\n"})
        allow = self.base / "allow"
        allow.write_text(allow_entry(f"wiki/{self.LEAK}", "password=hunter22", "key-value"))
        result = run_bin("wiki-lint", "--wiki", self.wiki, "--env-file", self.base / "none",
                         "--only", "secrets", "--allow-file", allow, "--paths-root", staged,
                         "--paths", staged / "wiki" / self.LEAK, staged / "local" / "notes.txt")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("local/notes.txt:1 E-SECRET", result.stdout)
        self.assertNotIn(self.LEAK, result.stdout)


class AllowHookTest(unittest.TestCase):
    """The pre-commit hook honours the staged copy of wiki/.secret-scan-allow."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = copy_harness(Path(self.tmp.name))
        patcher = mock.patch.dict(os.environ, GIT_ENV)
        patcher.start()
        self.addCleanup(patcher.stop)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        with redirect_stdout(io.StringIO()):
            init.main(["--root", str(self.root), "--non-interactive", "--hooks"])
        self.git("add", "-A")
        self.assertEqual(self.git("commit", "-qm", "init").returncode, 0)

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), "-c", "user.name=t",
                               "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false", *args],
                              capture_output=True, text=True)

    def test_an_allowed_line_commits_only_with_its_staged_exception(self):
        write_files(self.root, {"wiki/raw/2026-06-02-log.txt": "token: rotated yearly by cron\npassword=hunter22\n",
                                "local/notes.txt": "password=hunter22\n"})
        self.git("add", "wiki/raw/2026-06-02-log.txt", "local/notes.txt")
        blocked = self.git("commit", "-qm", "log")
        self.assertNotEqual(blocked.returncode, 0)
        self.assertIn("wiki/raw/2026-06-02-log.txt:2 E-SECRET", blocked.stdout + blocked.stderr)
        (self.root / "wiki" / ".secret-scan-allow").write_text(
            allow_entry("wiki/raw/2026-06-02-log.txt", "token: rotated yearly by cron", "key-value")
            + allow_entry("wiki/raw/2026-06-02-log.txt", "password=hunter22", "key-value")
            + allow_entry("local/notes.txt", "password=hunter22", "key-value"))
        still = self.git("commit", "-qm", "log")
        self.assertNotEqual(still.returncode, 0, "an unstaged exception must not count")
        self.git("add", "wiki/.secret-scan-allow")
        done = self.git("commit", "-qm", "log")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
