"""Hardening regressions: shapes that redaction, the lint or the hook once let through."""
import gzip
import io
import os
import re
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from tests.helpers import (GIT_ENV, append, clean_wiki, codes, copy_harness, lint, make_wiki,
                           run_bin, write_files)
from wikitools import frontmatter, init, redact


def r(text, **kw):
    return redact.redact(text, **kw)


class RedactionShapesTest(unittest.TestCase):
    def test_quoted_values_keep_their_quotes_and_rescan_clean(self):
        cases = {
            '<user name="a" password="kvattr8"/>\n': '<user name="a" password="<REDACTED:secret>"/>\n',
            'api_key: "abc123xyz"\n': 'api_key: "<REDACTED:secret>"\n',
            "  'dbpassword' => 'hunter2abc',\n": "  'dbpassword' => '<REDACTED:secret>',\n",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(r(text).text, expected)
                self.assertEqual(redact.scan(expected, redact.build_rules()), [])

    def test_crlf_lines_keep_their_line_endings(self):
        text = "password=crlfPass1\r\npassword_required: no\r\nline3\r\n"
        self.assertEqual(r(text).text, "password=<REDACTED:secret>\r\npassword_required: no\r\nline3\r\n")

    def test_more_homelab_secret_shapes(self):
        ghp = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"
        tg = "123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw"
        cases = {
            "pin=123456\n": "pin=<REDACTED:secret>\n",
            "password: 654321\n": "password: <REDACTED:secret>\n",
            "  - POSTGRES_PASSWORD=correct horse battery\n": "  - POSTGRES_PASSWORD=<REDACTED:secret>\n",
            "smb://user:p@ss2word@nas/share\n": "smb://user:<REDACTED:password>@nas/share\n",
            "mysql://u:ab/cd@db/x\n": "mysql://u:<REDACTED:password>@db/x\n",
            f"origin https://{ghp}@github.com/me/repo\n": "origin https://<REDACTED:token>@github.com/me/repo\n",
            f"https://api.telegram.org/bot{tg}/sendMessage\n": "https://api.telegram.org/bot<REDACTED:token>/sendMessage\n",
            "https://maps.example/api?key=AIzaQUERYKEY123&z=3\n": "https://maps.example/api?key=<REDACTED:secret>&z=3\n",
            "\toption key 'openwrtWifiKey11'\n": "\toption key '<REDACTED:secret>'\n",
            "wireless.default_radio0.key='uciWifiKey12'\n": "wireless.default_radio0.key='<REDACTED:secret>'\n",
            'pwhash = "$BALLOON-SHA256$v=1$s=1024,t=32$abc$def"\n': 'pwhash = "<REDACTED:secret>"\n',
            "rocommunity snmpComm13 10.0.0.0/24\n": "rocommunity <REDACTED:secret> 10.0.0.0/24\n",
            "username admin password 0 ciscoPw14\n": "username admin password 0 <REDACTED:secret>\n",
            "enable secret 5 $1$mERr$hx5rVt7rPNoS4wqbXKX7m0\n": "enable secret 5 <REDACTED:secret>\n",
            "admin:$apr1$saltsalt$htpasswdHASH16\n": "admin:<REDACTED:password-hash>\n",
            "mysql -uroot -pmysqlPw18 db\n": "mysql -uroot -p<REDACTED:password> db\n",
            "docker login -u me -p dockerPw19 registry\n": "docker login -u me -p <REDACTED:password> registry\n",
            "password:\n  multiLineYamlSecret22\n": "password:\n  <REDACTED:secret>\n",
            "password: |\n  line one secret\n  line two\nnext: 1\n": "password: |\n<REDACTED:secret>\nnext: 1\n",
            "tskey-auth-kTAILSCALE123-ABCDEFGHIJKLMNOP\n": "<REDACTED:token>\n",
            "<prv>LS0tLS1CRUdJTiBQUklWQVRFIEtFWS0tLS0t</prv>\n": "<prv><REDACTED:private-key></prv>\n",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(r(text).text, expected)

    def test_other_private_key_blocks(self):
        ovpn = "a\n-----BEGIN OpenVPN Static key V1-----\nabcd\n-----END OpenVPN Static key V1-----\nz\n"
        self.assertEqual(r(ovpn).text, "a\n<REDACTED:private-key>\nz\n")
        putty = ("PuTTY-User-Key-File-3: ssh-ed25519\nPrivate-Lines: 2\nAAAAIFake\nKeyMaterial==\n"
                 "Private-MAC: abc\n")
        self.assertEqual(r(putty).text, "PuTTY-User-Key-File-3: ssh-ed25519\nPrivate-Lines: 2\n"
                                        "<REDACTED:private-key>\nPrivate-MAC: abc\n")

    def test_false_positives_stay_untouched(self):
        for text in ["passthrough: enabled\n", "tokenizer: bert\n", "passwd: files systemd\n",
                     "Uses Bearer authentication for the API.\n", "ping: 12ms\n", "spinner=dots\n",
                     "token_ttl: 3600\n", "https://host:8443/@user\n",
                     "-----BEGIN PUBLIC KEY-----\nMFkw\n-----END PUBLIC KEY-----\n",
                     "ssh -p22 root@pve1\n", "tar -pxf backup.tar\n", "password: |\n"]:
            with self.subTest(text=text):
                self.assertEqual(r(text).text, text)

    def test_public_hostnames_and_more_mac_forms(self):
        text = ("host pve1.lab.lan and fictional-lab.duckdns.org\nmac aabb.ccdd.eeff\nhwaddr aabbccddeeff\n"
                "commit 0123456789ab\n")
        out = r(text, exposure="public")
        self.assertEqual(out.text, "host <HOST-1> and <HOST-2>\nmac <MAC-1>\nhwaddr <MAC-2>\n"
                                   "commit 0123456789ab\n")
        self.assertEqual(out.counts, {"secret": 0, "ip": 0, "mac": 2, "host": 2})

    def test_public_keeps_image_tags_and_debian_revisions(self):
        text = "image: vendor/controller:6.3.0.45\napt: controller 5.15.20.20-1 amd64\n"
        self.assertEqual(r(text, exposure="public").text, text)

    def test_keep_patterns_protect_unlabeled_versions(self):
        text = "NAS Controller 5.15.20.20 at 10.0.0.5\n"
        out = r(text, exposure="public", keep=[re.compile(r"Controller \S+")])
        self.assertEqual(out.text, "NAS Controller 5.15.20.20 at <IP-1>\n")


class EnvAndEntropyTest(unittest.TestCase):
    def test_env_values_are_secrets_unless_the_name_says_otherwise(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = Path(tmp) / ".env.local"
            env.write_text("MQTT_PW=mqttS3cretPW\nDB_PWD=dbS3cretPWD\nCLOUDFLARE_KEY=cfKeyAbc123456\n"
                           "WG_PIN=847261\nBACKUP_STORAGE=nas-backup\nPVE_SSH_PORT=22222\n"
                           "NAS_HOST=nas.lan.example\n")
            self.assertEqual(redact.load_env_literals(env),
                             ["mqttS3cretPW", "dbS3cretPWD", "cfKeyAbc123456", "847261"])
            self.assertEqual(redact.env_public_values(env),
                             {"BACKUP_STORAGE": "nas-backup", "NAS_HOST": "nas.lan.example"})

    def test_high_entropy_values_next_to_keys(self):
        text = ("ok: 1\nconfig_blob = aB3dE5fG7hJ9kL1mN2pQ4rS6tU8vW0xY\n"
                "digest: sha256:Ab12Cd34Ef56Gh78Ij90Kl12Mn34Op56Qr78\nuuid: 123e4567-e89b-12d3-a456-426614174000\n")
        self.assertEqual([h.line for h in redact.high_entropy(text)], [2])


class CaptureHardeningTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.wiki = make_wiki(self.base)
        self.env = self.base / ".env.local"

    def tearDown(self):
        self.tmp.cleanup()

    def cap(self, *args, stdin=None):
        return run_bin("wiki-capture", *args, "--wiki", self.wiki, "--env-file", self.env,
                       stdin=stdin, cwd=self.base)

    def capture_file(self, slug, data: bytes, *extra):
        path = self.base / f"{slug}.bin"
        path.write_bytes(data)
        return self.cap(slug, "--date", "2026-06-01", "--file", path, *extra)

    def meta(self, slug):
        text = (self.wiki / "sources" / f"2026-06-01-{slug}.md").read_text()
        return frontmatter.parse(frontmatter.split(text)[0])

    def test_utf16_with_bom_is_decoded_and_redacted(self):
        result = self.capture_file("ps-export", "password=hunter2utf16\r\nhost x\r\n".encode("utf-16"))
        self.assertEqual(result.returncode, 0, result.stderr)
        raw = (self.wiki / "raw" / "2026-06-01-ps-export.txt").read_bytes().decode("utf-8")
        self.assertEqual(raw, "password=<REDACTED:secret>\r\nhost x\r\n")
        self.assertTrue(self.meta("ps-export")["encoding"].startswith("utf-16"))

    def test_utf16_without_bom_is_detected(self):
        result = self.capture_file("reg", "password=hunter2utf16\n".encode("utf-16-le"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.wiki / "raw" / "2026-06-01-reg.txt").read_text(), "password=<REDACTED:secret>\n")

    def test_binary_input_is_refused(self):
        result = self.capture_file("blob", gzip.compress(b"password=hunter2\n"))
        self.assertEqual(result.returncode, 1)
        self.assertIn("binary", result.stderr)
        self.assertFalse((self.wiki / "raw" / "2026-06-01-blob.txt").exists())

    def test_non_utf8_falls_back_to_cp1252_and_says_so(self):
        result = self.capture_file("latin", b"Contrase\xf1a=se\xf1orPass1\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("cp1252", result.stderr)
        self.assertEqual((self.wiki / "raw" / "2026-06-01-latin.txt").read_text(encoding="utf-8"),
                         "Contraseña=señorPass1\n")
        self.assertEqual(self.meta("latin")["encoding"], "cp1252")

    def test_stale_source_page_is_refused(self):
        self.cap("leak", "--date", "2026-06-01", stdin="first\n")
        (self.wiki / "raw" / "2026-06-01-leak.txt").unlink()
        result = self.cap("leak", "--date", "2026-06-01", stdin="second\n")
        self.assertEqual(result.returncode, 2)
        self.assertIn("stale", result.stderr)
        self.assertFalse((self.wiki / "raw" / "2026-06-01-leak.txt").exists())

    def test_dry_run_counts_include_title_and_origin(self):
        result = self.cap("x", "--dry-run", "--title", "token=zzzzzz9", stdin="ok\n")
        self.assertIn("--- redactions: secret=1 ip=0 mac=0 host=0", result.stdout)

    def test_large_capture_warns(self):
        result = self.cap("big", "--date", "2026-06-01", stdin="line of log output\n" * 60000)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("large capture", result.stderr)

    def test_reverification_writes_a_dated_source_for_the_same_evidence(self):
        self.cap("node-status", "--date", "2026-06-01", stdin="same\n")
        result = self.cap("node-status", "--date", "2026-09-30", stdin="same\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("unchanged:", result.stdout)
        self.assertEqual(sorted(p.name for p in (self.wiki / "raw").iterdir()), ["2026-06-01-node-status.txt"])
        text = (self.wiki / "sources" / "2026-09-30-node-status.md").read_text()
        meta = frontmatter.parse(frontmatter.split(text)[0])
        self.assertEqual((meta["date"], meta["source"]), ("2026-09-30", "raw/2026-06-01-node-status.txt"))

    def test_allowlisted_env_value_in_output_is_noted(self):
        self.env.write_text("BACKUP_STORAGE=nas-backup\n")
        result = self.cap("pvesm", "--date", "2026-06-01", stdin="nas-backup nfs active\n")
        self.assertIn("BACKUP_STORAGE", result.stderr)

    def test_high_entropy_values_are_flagged_for_review(self):
        result = self.cap("blob", "--date", "2026-06-01", stdin="config_blob = aB3dE5fG7hJ9kL1mN2pQ4rS6tU8vW0xY\n")
        self.assertIn("random-looking", result.stderr)
        self.assertIn("line 1", result.stderr)


class LintHardeningTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.wiki = clean_wiki(self.base)

    def tearDown(self):
        self.tmp.cleanup()

    def test_encoding_problems_are_errors(self):
        write_files(self.wiki, {"raw/2026-06-02-ps.txt": "password=hunter2\n".encode("utf-16-le")})
        self.assertIn(("E-ENCODING", "raw/2026-06-02-ps.txt"), codes(lint(self.wiki)))

    def test_high_entropy_values_warn(self):
        append(self.wiki / "overview.md", "\n```\nconfig_blob = aB3dE5fG7hJ9kL1mN2pQ4rS6tU8vW0xY\n```\n")
        self.assertEqual(codes(lint(self.wiki)), [("W-ENTROPY", "overview.md")])

    def test_dot_directories_are_scanned_for_secrets(self):
        write_files(self.wiki, {".obsidian/plugins/copilot/data.json":
                                '{"openAIApiKey": "sk-proj-AAAAAAAAAAAAAAAAAAAAAAAAAAAA"}\n'})
        self.assertIn(("E-SECRET", ".obsidian/plugins/copilot/data.json"), codes(lint(self.wiki)))

    def test_passphrases_in_prose_are_flagged(self):
        append(self.wiki / "overview.md", "\n- password: correcthorsebatterystaple\n- password: required\n")
        found = [(f.code, f.line) for f in lint(self.wiki)]
        self.assertEqual(found, [("E-SECRET", 5)])

    def test_public_hostnames_are_exposure_errors(self):
        public = clean_wiki(self.base / "pub", exposure="public")
        append(public / "overview.md", "\nReachable at fictional-lab.duckdns.org.\n")
        self.assertEqual(codes(lint(public)), [("E-EXPOSURE", "overview.md")])


class HookHardeningTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = copy_harness(Path(self.tmp.name) / "repo")
        patcher = mock.patch.dict(os.environ, GIT_ENV)
        patcher.start()
        self.addCleanup(patcher.stop)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args, cwd=None):
        return subprocess.run(["git", "-C", str(cwd or self.root), "-c", "user.name=t",
                               "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false", *args],
                              capture_output=True, text=True)

    def run_init(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = init.main(["--root", str(self.root), "--non-interactive", *args])
        return code, out.getvalue(), err.getvalue()

    def test_secrets_under_local_are_blocked(self):
        self.assertEqual(self.run_init("--hooks")[0], 0)
        self.git("add", "-A")
        self.assertEqual(self.git("commit", "-qm", "init").returncode, 0)
        write_files(self.root, {"local/backup.sh": "PASSWORD=hunter2hunter2\n"})
        self.git("add", "-A")
        blocked = self.git("commit", "-qm", "leak")
        self.assertNotEqual(blocked.returncode, 0)
        self.assertIn("E-SECRET", blocked.stdout + blocked.stderr)

    def test_hooks_path_outside_the_repo_is_refused(self):
        outside = Path(self.tmp.name) / "global-hooks"
        outside.mkdir()
        self.git("config", "core.hooksPath", str(outside))
        code, _, err = self.run_init("--hooks")
        self.assertEqual(code, 1)
        self.assertIn("core.hooksPath", err)
        self.assertFalse((outside / "pre-commit").exists())

    def test_hook_without_the_harness_does_not_break_commits(self):
        other = Path(self.tmp.name) / "other"
        subprocess.run(["git", "init", "-q", str(other)], check=True)
        hook = other / ".git" / "hooks" / "pre-commit"
        hook.write_bytes((self.root / "templates" / "hooks" / "pre-commit").read_bytes())
        hook.chmod(0o755)
        write_files(other, {"wiki/page.md": "# page\n"})
        self.git("add", "-A", cwd=other)
        result = self.git("commit", "-qm", "x", cwd=other)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("wiki-lint not found", result.stderr)


class InitHardeningTest(unittest.TestCase):
    def test_language_is_validated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = copy_harness(Path(tmp))
            err = io.StringIO()
            with redirect_stderr(err), self.assertRaises(SystemExit) as cm:
                init.main(["--root", str(root), "--non-interactive", "--language", "[pt"])
            self.assertEqual(cm.exception.code, 2)
            self.assertFalse((root / "wiki").exists())

    def test_creates_the_instance_rules_file_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = copy_harness(Path(tmp))
            with redirect_stdout(io.StringIO()) as out:
                init.main(["--root", str(root), "--non-interactive"])
            rules = root / ".claude" / "rules" / "local.md"
            self.assertIn("created: .claude/rules/local.md", out.getvalue())
            self.assertIn("local/docs/specs/", rules.read_text())
            rules.write_text("# mine\n")
            with redirect_stdout(io.StringIO()):
                init.main(["--root", str(root), "--non-interactive"])
            self.assertEqual(rules.read_text(), "# mine\n")



CHANGE = """\
    ---
    date: 2026-06-01
    targets: [entities/host-pve1]
    outcome: done
    rollback: snapshot
    baseline: sources/2026-06-01-node-status
    after: sources/2026-06-01-node-status
    ---

    # Upgrade pve1
    """


class ParserHardeningTest(unittest.TestCase):
    def test_bom_before_frontmatter(self):
        self.assertEqual(frontmatter.split("﻿---\na: 1\n---\nx\n"), ("a: 1", "x\n", 4))

    def test_yaml_block_lists(self):
        self.assertEqual(frontmatter.parse('targets:\n  - entities/a\n  - "entities/b"\nnext: 1\n'),
                         {"targets": ["entities/a", "entities/b"], "next": 1})

    def test_stray_list_item_is_an_error(self):
        with self.assertRaises(frontmatter.FrontmatterError):
            frontmatter.parse("- a\n")

    def test_quoted_strings_round_trip(self):
        data = {"title": 'Router "edge" \\ backslash', "note": "a # b", "single": "it's"}
        fm, _, _ = frontmatter.split(frontmatter.dumps(data))
        self.assertEqual(frontmatter.parse(fm), data)
        self.assertEqual(frontmatter.parse("a: 'it''s'\n"), {"a": "it's"})


class LintStructureHardeningTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.wiki = clean_wiki(self.base)

    def tearDown(self):
        self.tmp.cleanup()

    def link(self, page):
        append(self.wiki / "index.md", f"- [[{page}]] — x\n")
        append(self.wiki / "entities" / "host-pve1.md", f"\nSee [[{page}]].\n")

    def add_change(self, text):
        write_files(self.wiki, {"changes/2026-06-01-upgrade.md": text})
        self.link("changes/2026-06-01-upgrade")

    def test_broken_frontmatter_on_any_page(self):
        write_files(self.wiki, {"concepts/c.md": "---\nnot a pair\n---\n# C\n"})
        self.link("concepts/c")
        self.assertIn(("E-FRONTMATTER", "concepts/c.md"), codes(lint(self.wiki)))

    def test_links_cannot_escape_the_wiki(self):
        write_files(self.base, {"README.md": "# readme\n"})
        append(self.wiki / "overview.md", "\nSee [[../README]].\n")
        self.assertEqual(codes(lint(self.wiki)), [("E-LINK", "overview.md")])

    def test_sources_cannot_escape_the_wiki(self):
        write_files(self.base.parent, {"x.txt": "x\n"})
        path = self.wiki / "sources" / "2026-06-01-node-status.md"
        path.write_text(path.read_text().replace("source: raw/2026-06-01-node-status.txt",
                                                 "source: raw/../../../x.txt"))
        self.assertIn(("E-SRC-FIELD", "sources/2026-06-01-node-status.md"), codes(lint(self.wiki)))

    def test_schema_keys_missing_from_the_template_are_reported(self):
        agents = self.wiki / "AGENTS.md"
        agents.write_text(agents.read_text().replace("pending_after_days: 14\n", ""))
        found = [(f.level, f.code) for f in lint(self.wiki)]
        self.assertEqual(found, [("INFO", "I-SCHEMA")])

    def test_after_the_fact_record_needs_a_reason_instead_of_a_baseline(self):
        without = CHANGE.replace("    baseline: sources/2026-06-01-node-status\n", "")
        self.add_change(without)
        self.assertIn(("E-CHANGE-FIELD", "changes/2026-06-01-upgrade.md"), codes(lint(self.wiki, "2026-06-10")))
        self.add_change(without.replace("    after:", "    baseline_unavailable: changed before the wiki existed\n    after:"))
        self.assertEqual(lint(self.wiki, "2026-06-10"), [])

    def test_specs_and_plans_must_exist(self):
        self.add_change(CHANGE.replace("    after:", "    specs: [local/docs/specs/backup.md]\n    after:"))
        self.assertEqual(codes(lint(self.wiki, "2026-06-10")), [("E-CHANGE-FIELD", "changes/2026-06-01-upgrade.md")])
        write_files(self.base, {"local/docs/specs/backup.md": "# spec\n"})
        self.assertEqual(lint(self.wiki, "2026-06-10"), [])

    def test_diagnose_is_a_log_operation(self):
        append(self.wiki / "log.md", "\n## [2026-06-02] diagnose | Backup job failing\n")
        self.assertEqual(lint(self.wiki), [])



CORPUS = """\
-----BEGIN OPENSSH PRIVATE KEY-----
b3BlbnNzaA==
-----END OPENSSH PRIVATE KEY-----
Authorization: Bearer abcdef1234567890
Authorization: Basic YWRtaW46aHVudGVyMg==
token eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0In0.c2lnbmF0dXJlX2hlcmU
remote https://admin:hunter2secret@git.lab/x.git
smb://user:p@ss2word@nas/share
PVE_ROOT_PASSWORD=s3cr3t-value
api_key: "abc123xyz"
  'dbpassword' => 'hunter2abc',
<user name="a" password="kvattr8"/>
<password>Hunter2x</password>
  - POSTGRES_PASSWORD=correct horse battery
password:
  multiLineYamlSecret22
psk="correct-horse-99"
PresharedKey = aGVsbG8gd29ybGQ=
\toption key 'openwrtWifiKey11'
rocommunity snmpComm13 10.0.0.0/24
username admin password 0 ciscoPw14
admin:$apr1$saltsalt$htpasswdHASH16
root:$6$salt$hashhashhash:19500:0:99999:7:::
sshpass -p Hunter2x ssh root@pve1
mysql -uroot -pmysqlPw18 db
curl -u admin:Hunter2x https://nas
https://maps.example/api?key=AIzaQUERYKEY123&z=3
pin=123456
| password | CorrectHorse99 |
"""


class RescanPropertyTest(unittest.TestCase):
    def test_redacted_output_rescans_clean(self):
        for exposure in ("private", "public"):
            with self.subTest(exposure=exposure):
                out = redact.redact(CORPUS, exposure=exposure)
                rules = redact.build_rules(exposure=exposure)
                self.assertEqual(redact.scan(out.text, rules), [], out.text)
                self.assertEqual(redact.redact(out.text, exposure=exposure).text, out.text)
                self.assertGreaterEqual(out.counts["secret"], 25)


if __name__ == "__main__":
    unittest.main()
