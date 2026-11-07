import re
import tempfile
import unittest
from pathlib import Path

from wikitools import redact


def r(text, **kw):
    return redact.redact(text, **kw)


class SecretRedactionTest(unittest.TestCase):
    def test_private_key_block(self):
        text = "a\n-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaA==\n-----END OPENSSH PRIVATE KEY-----\nz\n"
        out = r(text)
        self.assertEqual(out.text, "a\n<REDACTED:private-key>\nz\n")
        self.assertEqual(out.counts, {"secret": 1, "ip": 0, "mac": 0, "host": 0})

    def test_bearer_token(self):
        out = r("Authorization: Bearer abcdef123456\n")
        self.assertEqual(out.text, "Authorization: Bearer <REDACTED:token>\n")

    def test_jwt(self):
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0In0.c2lnbmF0dXJlX2hlcmU"
        self.assertEqual(r(f"got {jwt} back\n").text, "got <REDACTED:token> back\n")

    def test_url_credentials(self):
        out = r("remote: https://admin:hunter2secret@git.lab/x.git\n")
        self.assertEqual(out.text, "remote: https://admin:<REDACTED:password>@git.lab/x.git\n")

    def test_key_value_forms(self):
        cases = {
            "PVE_ROOT_PASSWORD=s3cr3t-value\n": "PVE_ROOT_PASSWORD=<REDACTED:secret>\n",
            'api_key: "abc123xyz"\n': 'api_key: "<REDACTED:secret>"\n',
            '{"token": "abc123xyz"}': '{"token": "<REDACTED:secret>"}',
            "--password=abc123xyz\n": "--password=<REDACTED:secret>\n",
            "https://h/api?token=abc123xyz&x=1\n": "https://h/api?token=<REDACTED:secret>&x=1\n",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(r(text).text, expected)

    def test_key_value_leaves_non_secrets_alone(self):
        for text in ["PasswordAuthentication no\n", "password: <REDACTED:secret>\n",
                     "token_ttl: 3600\n", "password: ${DB_PASSWORD}\n", "secret: true\n",
                     "password: ''\n", "Enter password:\n", "api_key: ********\n"]:
            with self.subTest(text=text):
                out = r(text)
                self.assertEqual(out.text, text)
                self.assertEqual(out.counts["secret"], 0)

    def test_a_pass_status_line_is_not_a_password(self):
        # test and check logs: "PASS: <what passed>", with the uppercase word and a colon
        for text in ["PASS: web answers 200\n", "PASS: test_login\n", "  PASS: pve1 dispatcher ok\n",
                     "check PASS: storage local-lvm\n"]:
            with self.subTest(text=text):
                out = r(text)
                self.assertEqual(out.text, text)
                self.assertEqual(out.counts["secret"], 0)
        for text, expected in {"PASS=hunter22\n": "PASS=<REDACTED:secret>\n",
                               "pass: hunter22\n": "pass: <REDACTED:secret>\n",
                               "Pass: hunter22\n": "Pass: <REDACTED:secret>\n",
                               "SMTP_PASS: hunter22\n": "SMTP_PASS: <REDACTED:secret>\n"}.items():
            with self.subTest(text=text):
                self.assertEqual(r(text).text, expected)

    def test_env_literals(self):
        out = r("login as root with Tr0ub4dor&3 today\n", literals=["Tr0ub4dor&3"])
        self.assertEqual(out.text, "login as root with <REDACTED:secret> today\n")
        self.assertEqual(r("abc abc\n", literals=["abc"]).text, "abc abc\n")

    def test_custom_patterns(self):
        out = r("wifi psk lab-psk-9f8e7d\n", custom=[re.compile(r"lab-psk-\w+")])
        self.assertEqual(out.text, "wifi psk <REDACTED:custom>\n")


class LoaderTest(unittest.TestCase):
    def test_load_env_literals(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = Path(tmp) / ".env.local"
            env.write_text("# comment\nPVE_ROOT_PASSWORD='Tr0ub4dor&3'\n"
                           "export API_TOKEN=tok_123456789\nPVE_SSH_PORT=22\nSHORT_SECRET=abc\n")
            self.assertEqual(redact.load_env_literals(env), ["Tr0ub4dor&3", "tok_123456789"])
            self.assertEqual(redact.load_env_literals(Path(tmp) / "missing"), [])
            self.assertEqual(redact.load_env_literals(None), [])

    def test_load_custom_patterns(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".capture-patterns"
            path.write_text("# comment\n\nlab-psk-\\w+\n")
            self.assertEqual([p.pattern for p in redact.load_custom_patterns(path)], ["lab-psk-\\w+"])
            path.write_text("# ok\n([unclosed\n")
            with self.assertRaises(redact.PatternError) as cm:
                redact.load_custom_patterns(path)
            self.assertEqual(cm.exception.line, 2)
            self.assertEqual(redact.load_custom_patterns(Path(tmp) / "missing"), [])


class ExposureTest(unittest.TestCase):
    def test_public_numbers_addresses_consistently(self):
        text = ("a 10.0.0.5 b 10.0.0.6 c 10.0.0.5\n"
                "hwaddr=BC:24:11:00:01:01 bc:24:11:00:01:01\n"
                "fe80::1ff:fe23:4567:890a\n")
        out = r(text, exposure="public")
        self.assertEqual(out.text, "a <IP-1> b <IP-2> c <IP-1>\nhwaddr=<MAC-1> <MAC-1>\n<IPV6-1>\n")
        self.assertEqual(out.counts, {"secret": 0, "ip": 4, "mac": 2, "host": 0})

    def test_public_keeps_versions_loopback_masks_and_times(self):
        text = ("controller_version: 6.3.0.45\nv5.15.20.20\nVersion 5.15.20.20\n127.0.0.1\n"
                "0.0.0.0\n255.255.255.0\nDate: 09:12:44\nstd::string\n::1\n")
        self.assertEqual(r(text, exposure="public").text, text)

    def test_private_keeps_addresses(self):
        self.assertEqual(r("ip 10.0.0.5\n").text, "ip 10.0.0.5\n")


class ScanTest(unittest.TestCase):
    def test_scan_reports_lines_without_modifying(self):
        hits = redact.scan("ok\npassword=hunter22\nok\n", redact.build_rules())
        self.assertEqual([(h.line, h.rule, h.bucket) for h in hits], [(2, "key-value", "secret")])

    def test_scan_exposure(self):
        hits = redact.scan("x\ngw 10.0.0.1\n", redact.EXPOSURE_RULES)
        self.assertEqual([(h.line, h.rule) for h in hits], [(2, "ipv4")])

    def test_key_value_rule_is_not_prose_safe(self):
        by_name = {rule.name: rule for rule in redact.build_rules()}
        self.assertFalse(by_name["key-value"].prose_safe)
        self.assertTrue(by_name["jwt"].prose_safe)


class RedactionRegressionTest(unittest.TestCase):
    """Values redaction once missed or mangled."""

    def test_arrow_separator_in_php_config(self):
        text = ("  'dbpassword' => 'hunter2abc',\n"
                "  'passwordsalt' => 'Zx9mQ2pL7wR4',\n"
                "  'secret' => 'aB3dE5fG7hJ9',\n")
        out = r(text)
        self.assertEqual(out.text, "  'dbpassword' => '<REDACTED:secret>',\n"
                                   "  'passwordsalt' => '<REDACTED:secret>',\n"
                                   "  'secret' => '<REDACTED:secret>',\n")
        self.assertEqual(out.counts["secret"], 3)
        self.assertEqual([h.line for h in redact.scan(text, redact.build_rules())], [1, 2, 3])

    def test_values_at_line_start_are_redacted_to_end_of_line(self):
        cases = {
            "password = correct horse battery staple\n": "password = <REDACTED:secret>\n",
            "password=Tr0ub4dor&3xyz\n": "password=<REDACTED:secret>\n",
            "db_pass: P@ss,word99\n": "db_pass: <REDACTED:secret>\n",
            "  api_key: abc123def # rotated in June\n": "  api_key: <REDACTED:secret> # rotated in June\n",
            'export API_TOKEN="tok 123"\n': 'export API_TOKEN="<REDACTED:secret>"\n',
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(r(text).text, expected)

    def test_homelab_secret_shapes(self):
        cases = {
            "PresharedKey = aGVsbG8gd29ybGQ=\n": "PresharedKey = <REDACTED:secret>\n",
            '  psk="correct-horse-99"\n': '  psk="<REDACTED:secret>"\n',
            "wpa2-pre-shared-key=Sup3rS3cret\n": "wpa2-pre-shared-key=<REDACTED:secret>\n",
            "community: s3cretCommunity\n": "community: <REDACTED:secret>\n",
            "> Authorization: Basic YWRtaW46aHVudGVyMg==\n": "> Authorization: Basic <REDACTED:token>\n",
            "set-cookie PVEAuthCookie=PVE:root@pam:65A1B2C3::sig\n": "set-cookie PVEAuthCookie=<REDACTED:secret>\n",
            "sshpass -p Hunter2x ssh root@pve1\n": "sshpass -p <REDACTED:password> ssh root@pve1\n",
            "mysqldump --password Hunter2x db\n": "mysqldump --password <REDACTED:password> db\n",
            "curl -u admin:Hunter2x https://nas\n": "curl -u admin:<REDACTED:password> https://nas\n",
            "<password>Hunter2x</password>\n": "<password><REDACTED:secret></password>\n",
            "root:$6$salt$hashhashhash:19500:0:99999:7:::\n": "root:<REDACTED:password-hash>:19500:0:99999:7:::\n",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(r(text).text, expected)

    def test_pgp_and_truncated_private_keys(self):
        pgp = "a\n-----BEGIN PGP PRIVATE KEY BLOCK-----\nlQOYBF==\n-----END PGP PRIVATE KEY BLOCK-----\nz\n"
        self.assertEqual(r(pgp).text, "a\n<REDACTED:private-key>\nz\n")
        cut = "log line\n-----BEGIN RSA PRIVATE KEY-----\nMIIEow==\n"
        self.assertEqual(r(cut).text, "log line\n<REDACTED:private-key>")

    def test_docker_user_flag_is_not_a_password(self):
        self.assertEqual(r("docker run -u 1000:1000 img\n").text, "docker run -u 1000:1000 img\n")

    def test_env_literals_with_trailing_comments(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = Path(tmp) / ".env.local"
            env.write_text("PVE_ROOT_PASSWORD=Tr0ub4dor3xyz # root on pve1\n"
                           'HA_TOKEN="abc123456789"  # long-lived token\n'
                           "WIFI_PSK='x y z 123'\n")
            self.assertEqual(redact.load_env_literals(env), ["Tr0ub4dor3xyz", "abc123456789", "x y z 123"])

    def test_public_keeps_more_version_contexts(self):
        text = ("firmware: 1.0.3.12\nfw 2.1.0.4\nbuild 5.15.20.20\nrelease 6.3.0.45\n"
                "ii  nas-controller  5.15.20.20  amd64\n")
        self.assertEqual(r(text, exposure="public").text, text)


if __name__ == "__main__":
    unittest.main()
