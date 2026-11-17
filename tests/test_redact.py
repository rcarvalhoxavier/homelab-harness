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


# Invented values, built in pieces like the token-shaped strings above.
UUID = "0a1b2c3d-" + "4e5f-4a6b-8c7d-" + "9e0f1a2b3c4d"
BCRYPT = "$2y$10$" + "abcdefghijklmnopqrstuv" + "wxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0"


class SecretShapeTest(unittest.TestCase):
    """Secret shapes from homelab configuration files and commands, each with lines that look
    alike and must stay: evidence is useless if ordinary lines are destroyed."""

    def check(self, cases, untouched):
        for text, expected in cases.items():
            with self.subTest(text=text):
                out = r(text)
                self.assertEqual(out.text, expected)
                self.assertGreater(out.counts["secret"], 0)
        for text in untouched:
            with self.subTest(untouched=text):
                out = r(text)
                self.assertEqual(out.text, text)
                self.assertEqual(out.counts["secret"], 0)

    def test_proxmox_api_token_secret(self):
        table = ("│ full-tokenid │ root@pam!monitor │\n"
                 "│ info         │ {\"privsep\":1}   │\n"
                 f"│ value        │ {UUID} │\n")
        json = '{"full-tokenid":"root@pam!monitor","info":{"privsep":1},"value":"' + UUID + '"}\n'
        yaml = f"---\nfull-tokenid: root@pam!monitor\ninfo:\n   privsep: '1'\nvalue: {UUID}\n"
        self.check({
            table: table.replace(UUID, "<REDACTED:token>"),
            json: json.replace(UUID, "<REDACTED:token>"),
            yaml: yaml.replace(UUID, "<REDACTED:token>"),
            f"root@pam!monitor {UUID}\n": "root@pam!monitor <REDACTED:token>\n",
            f"backup@pve!pbs-sync {UUID}\n": "backup@pve!pbs-sync <REDACTED:token>\n",
            f"Authorization: PVEAPIToken=root@pam!monitor={UUID}\n": "Authorization: PVEAPIToken=<REDACTED:secret>\n",
        }, [
            f"smbios1: uuid={UUID}\n",
            f"UUID={UUID} / ext4 defaults 0 1\n",
            f"vmgenid: {UUID}\n",
            f"│ value        │ {UUID} │\n",               # no token id in the text
            '{"id":"sensor.cpu","value":"' + UUID + '"}\n',
            "│ full-tokenid │ root@pam!monitor │\n",
        ])

    def test_url_credentials_with_an_empty_user_name(self):
        self.check({
            "redis://:Hunter2pass@cache:6379/0\n": "redis://:<REDACTED:password>@cache:6379/0\n",
            "REDIS_URL=redis://:Hunter2pass@cache\n": "REDIS_URL=redis://:<REDACTED:password>@cache\n",
        }, ["redis://cache:6379/0\n", "redis://cache:6379\n", "https://host:8443/@user\n"])

    def test_cloud_init_password(self):
        self.check({
            "qm set 101 --cipassword Hunter2pass\n": "qm set 101 --cipassword <REDACTED:password>\n",
            "qm set 101 --cipassword=Hunter2pass\n": "qm set 101 --cipassword=<REDACTED:secret>\n",
            "qm set 101 --cipassword 'two words'\n": "qm set 101 --cipassword '<REDACTED:password>'\n",
        }, ["qm set 101 --ciuser admin\n", "cipassword: **********\n",
            "qm set 101 --ipconfig0 ip=dhcp\n"])

    def test_snmp_community_in_snmpd_conf(self):
        self.check({
            "com2sec readonly default snmpComm13\n": "com2sec readonly default <REDACTED:secret>\n",
            "com2sec6 -Cn ctx local ::1 snmpComm13\n": "com2sec6 -Cn ctx local ::1 <REDACTED:secret>\n",
        }, ["#       sec.name  source          community\n", "group MyROGroup v2c readonly\n"])

    def test_snmp_community_and_passphrases_on_the_command_line(self):
        self.check({
            "snmpwalk -v2c -c snmpComm13 10.0.0.2\n": "snmpwalk -v2c -c <REDACTED:secret> 10.0.0.2\n",
            "snmpget -v2c -csnmpComm13 nas sysUpTime.0\n": "snmpget -v2c -c<REDACTED:secret> nas sysUpTime.0\n",
            "snmpbulkwalk -v2c -c 'snmpComm13' sw1 ifTable\n": "snmpbulkwalk -v2c -c '<REDACTED:secret>' sw1 ifTable\n",
            "snmpset -v1 -c snmpComm13 sw1 sysName.0 s lab\n": "snmpset -v1 -c <REDACTED:secret> sw1 sysName.0 s lab\n",
            "snmpwalk -v3 -l authPriv -u mon -a SHA -A authPass99 -x AES -X privPass99 nas\n":
                "snmpwalk -v3 -l authPriv -u mon -a SHA -A <REDACTED:secret> -x AES -X <REDACTED:secret> nas\n",
        }, ["ssh -c aes256-ctr root@pve1\n", "ping -c 3 nas\n", "tar -czf backup.tgz etc\n",
            "tar -c -f backup.tar etc\n", "snmpwalk -v2c -Cc nas\n"])

    def test_wpa_psk_in_network_interfaces(self):
        self.check({
            "    wpa-psk wifiSecret99\n": "    wpa-psk <REDACTED:secret>\n",
            '    wpa-psk "wifi secret 99"\n': '    wpa-psk "<REDACTED:secret>"\n',
            "wpa_passphrase=wifiSecret99\n": "wpa_passphrase=<REDACTED:secret>\n",
            '  psk="wifiSecret99"\n': '  psk="<REDACTED:secret>"\n',
        }, ["    wpa-ssid HomeNet\n", "    wpa-key-mgmt WPA-PSK\n",
            "    wpa-conf /etc/wpa_supplicant/wpa_supplicant.conf\n", "key_mgmt=WPA-PSK\n"])

    def test_space_separated_password(self):
        self.check({
            "password hunter2abc\n": "password <REDACTED:secret>\n",
            "  password    hunter2abc\n": "  password    <REDACTED:secret>\n",
            'password "two words 9"\n': 'password "<REDACTED:secret>"\n',
        }, ["PasswordAuthentication no\n", "PermitEmptyPasswords no\n",
            "password requisite pam_pwquality.so retry=3\n",
            "password [success=1 default=ignore] pam_unix.so obscure yescrypt\n",
            "password required\n", "password changed\n",
            "The password is rotated yearly.\n", "password vaults.\n", 'passwordeval "gpg -q -d ~/.msmtp-pass.gpg"\n',
            "passwd root\n"])

    def test_netrc_password(self):
        self.check({
            "machine nas.lab login admin password hunter2abc\n":
                "machine nas.lab login admin password <REDACTED:secret>\n",
            "default login anonymous password hunter2abc\n":
                "default login anonymous password <REDACTED:secret>\n",
            "machine nas.lab\n  login admin\n  password hunter2abc\n":
                "machine nas.lab\n  login admin\n  password <REDACTED:secret>\n",
            "  login admin password hunter2abc\n": "  login admin password <REDACTED:secret>\n",
        }, ["machine nas.lab login admin\n", "The default password policy applies.\n"])

    def test_postfix_sasl_passwd(self):
        self.check({
            "[smtp.example.com]:587 me@example.com:hunter2abc\n":
                "[smtp.example.com]:587 me@example.com:<REDACTED:secret>\n",
            "smtp.example.com relay-user:hunter2abc\n": "smtp.example.com relay-user:<REDACTED:secret>\n",
            "example.com:587 relay-user:hunter2abc\n": "example.com:587 relay-user:<REDACTED:secret>\n",
        }, ["FROM debian:bookworm\n", "image: nginx:1.25\n", "relayhost = [smtp.example.com]:587\n",
            "10.0.0.5 nas.lab.example\n", "docker.io/library/nginx:1.25 up 3 days\n",
            ".I http://www.sane-project.org/\n", "backup.example.com nas:/export/backup\n",
            "    slave.pcm plug:dmixer\n", '    slave.pcm "plughw:0,0"\n'])

    def test_chpasswd_input(self):
        self.check({
            "echo admin:hunter2abc | chpasswd\n": "echo admin:<REDACTED:password> | chpasswd\n",
            "echo 'root:hunter2abc' | sudo chpasswd\n": "echo 'root:<REDACTED:password>' | sudo chpasswd\n",
            "chpasswd <<< 'admin:hunter2abc'\n": "chpasswd <<< 'admin:<REDACTED:password>'\n",
        }, ["echo done | tee -a log\n", "chpasswd --help\n", "echo 10:30 | logger\n"])

    def test_age_secret_key(self):
        key = "AGE-SECRET-KEY-1" + "QWERTYUPASDFGHJKLZXCVNM023456789" + "QWERTYUPASDFGHJKLZXCVN"
        recipient = "age1" + "ql3z7hjy54pw3hyww5ayyfg7zqgvc7w3j2elw8zmrj2kg5sfn9aqmcac8p"
        self.check({
            f"{key}\n": "<REDACTED:private-key>\n",
            f"# public key: {recipient}\n{key}\n": f"# public key: {recipient}\n<REDACTED:private-key>\n",
        }, [f"# public key: {recipient}\n", f"recipients: {recipient}\n"])

    def test_bcrypt_hash_outside_htpasswd(self):
        doubled = BCRYPT.replace("$", "$$")
        self.check({
            f"  hash: {BCRYPT}\n": "  hash: <REDACTED:password-hash>\n",
            f"traefik.http.middlewares.auth.basicauth.users=admin:{doubled}\n":
                "traefik.http.middlewares.auth.basicauth.users=admin:<REDACTED:password-hash>\n",
            f'{{"hash": "{BCRYPT.replace("$2y", "$2b")}"}}\n': '{"hash": "<REDACTED:password-hash>"}\n',
        }, ["echo $2\n", "awk '{print $2}' file\n", "it costs $2 per month\n", "$2a is a label\n"])

    def test_hex_or_random_value_of_a_key_named_key(self):
        self.check({
            "MEILI_MASTER_KEY=0123456789abcdef0123456789abcdef\n": "MEILI_MASTER_KEY=<REDACTED:secret>\n",
            "ENCRYPTION_KEY: 0123456789ABCDEF0123456789ABCDEF\n": "ENCRYPTION_KEY: <REDACTED:secret>\n",
            'MEILI_MASTER_KEY="aB3dE5fG7hJ9kL1mN2pQ4rS6"\n': 'MEILI_MASTER_KEY="<REDACTED:secret>"\n',
            "  app-key: aB3dE5fG7hJ9kL1mN2pQ4rS6\n": "  app-key: <REDACTED:secret>\n",
        }, ["SSH_KEY=/root/.ssh/id_ed25519\n", "SSH_KEY=/home/Admin2/.ssh/id_ed25519\n",
            "SORT_KEY=name\n", "GPG_KEY=0D96DF4D4110E5C43FBFB17F2D347EA6AA65421D\n",
            "PUBLIC_KEY=0123456789abcdef0123456789abcdef\n", "CACHE_KEY=short\n",
            "DB_KEY_ID=0123456789abcdef0123\n", "primary_key: id\n"])

    def test_chat_webhook_urls(self):
        slack = "https://hooks.slack.com/services/" + "T0FAKE000/B0FAKE000/" + "aB3dE5fG7hJ9kL1mN2pQ4rS6"
        discord = ("https://discord.com/api/webhooks/" + "123456789012345678/"
                   + "aB3dE5fG7hJ9kL1mN2pQ4rS6tU8vW0xY_-z")
        self.check({
            f"SLACK_WEBHOOK_URL={slack}\n": "SLACK_WEBHOOK_URL=https://hooks.slack.com/services/<REDACTED:token>\n",
            f"url: {discord}\n": "url: https://discord.com/api/webhooks/123456789012345678/<REDACTED:token>\n",
        }, ["see https://hooks.slack.com/ for the docs\n", "https://discord.com/channels/123/456\n"])


if __name__ == "__main__":
    unittest.main()
