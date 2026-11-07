import hashlib
import unittest

from tests import pvefixtures as fx
from tests.toolkit import Lab

D = "/etc/apt/sources.list.d"
# untranslated messages, so the signature scan can read them
UPDATE = "env LC_ALL=C DEBIAN_FRONTEND=noninteractive apt-get update"
INSTALL_RE = r"re:install -o root -g root -m 0644 /tmp/homelab-put\.[A-Za-z0-9]{8} /etc/apt/sources\.list\.d/.*"
RM_RE = r"re:rm -f /tmp/homelab-put\.[A-Za-z0-9]{8}"


class RepoSetupTest(unittest.TestCase):
    def lab_for(self, version: str) -> Lab:
        lab = Lab()
        self.addCleanup(lab.close)
        fx.load(lab, version)
        return lab

    def test_pve8_dry_run(self):
        lab = self.lab_for("8")
        result = lab.run("pve-repo-setup", "pve1", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("check: Proxmox VE 8: ok\ncheck: Debian bookworm: ok\n", result.stdout)
        self.assertNotIn("experimental", result.stdout)
        self.assertIn(f"step 1/4: put {D}/ceph.list (mode 0644) on pve1-admin\n"
                      "    | # deb https://enterprise.proxmox.com/debian/ceph-quincy bookworm enterprise\n", result.stdout)
        self.assertIn(f"step 3/4: put {D}/pve-no-subscription.list (mode 0644) on pve1-admin\n"
                      "    | deb http://download.proxmox.com/debian/pve bookworm pve-no-subscription\n", result.stdout)
        self.assertIn(f"step 4/4: ssh pve1-admin -- {UPDATE}\n", result.stdout)
        self.assertEqual(lab.commands("admin"), [])

    def test_pve9_dry_run(self):
        lab = self.lab_for("9")
        result = lab.run("pve-repo-setup", "pve1", "--dry-run")
        self.assertIn("check: Proxmox VE 9: ok\ncheck: Proxmox VE 9 support is experimental (not yet verified on a "
                      "real node): WARNING\n", result.stdout)
        self.assertIn(f"step 2/4: put {D}/pve-enterprise.sources (mode 0644) on pve1-admin\n"
                      "    | Types: deb\n    | URIs: https://enterprise.proxmox.com/debian/pve\n"
                      "    | Suites: trixie\n    | Components: pve-enterprise\n"
                      "    | Signed-By: /usr/share/keyrings/proxmox-archive-keyring.gpg\n    | Enabled: no\n",
                      result.stdout)
        self.assertIn(f"step 3/4: put {D}/pve-no-subscription.sources (mode 0644) on pve1-admin\n"
                      "    | Types: deb\n    | URIs: http://download.proxmox.com/debian/pve\n    | Suites: trixie\n"
                      "    | Components: pve-no-subscription\n"
                      "    | Signed-By: /usr/share/keyrings/proxmox-archive-keyring.gpg\n", result.stdout)

    def test_already_configured(self):
        lab = self.lab_for("8")
        lab.respond("pve1", f"cat {D}/ceph.list", stdout="# deb https://enterprise.proxmox.com/debian/ceph-quincy bookworm enterprise\n")
        lab.respond("pve1", f"cat {D}/pve-enterprise.list", stdout="# deb https://enterprise.proxmox.com/debian/pve bookworm pve-enterprise\n")
        lab.respond("pve1", f"ls {D}", stdout="ceph.list\npve-enterprise.list\npve-no-subscription.list\n")
        lab.respond("pve1", f"cat {D}/pve-no-subscription.list",
                    stdout="deb http://download.proxmox.com/debian/pve bookworm pve-no-subscription\n")
        result = lab.run("pve-repo-setup", "pve1", "--yes")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("already configured", result.stdout)
        self.assertEqual(lab.commands("admin"), [])

    def test_a_nosub_entry_for_another_suite_is_not_configured(self):
        # half-way through an 8 to 9 upgrade: trixie, with the bookworm no-subscription entry left
        for one_line in (False, True):
            with self.subTest(one_line=one_line):
                lab = self.lab_for("9")
                if one_line:
                    name, text = ("pve-no-subscription.list",
                                  "deb [arch=amd64] http://download.proxmox.com/debian/pve bookworm pve-no-subscription\n")
                else:
                    name, text = ("pve-no-subscription.sources",
                                  "Types: deb\nURIs: http://download.proxmox.com/debian/pve\nSuites: bookworm\n"
                                  "Components: pve-no-subscription\n")
                listing = lab.responses["pve1"][f"ls {D}"]["stdout"]
                lab.respond("pve1", f"ls {D}", stdout=listing + name + "\n")
                lab.respond("pve1", f"cat {D}/{name}", stdout=text)
                result = lab.run("pve-repo-setup", "pve1", "--dry-run")
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn(f"check: {D}/{name} enables pve-no-subscription for bookworm, not trixie: "
                              "fix it by hand first: FAILED", result.stdout)
                self.assertNotIn("already configured", result.stdout)
                self.assertNotIn("step 1/", result.stdout)

    def configured_after(self, lab: Lab, update_output: str):
        lab.respond("pve1", INSTALL_RE)
        lab.respond("pve1", RM_RE)
        lab.respond("pve1", UPDATE, stdout=update_output)
        lab.respond_seq("pve1", f"ls {D}", {"stdout": "ceph.list\npve-enterprise.list\n"},
                        {"stdout": "ceph.list\npve-enterprise.list\npve-no-subscription.list\n"})
        for name, line in (("ceph.list", "deb https://enterprise.proxmox.com/debian/ceph-quincy bookworm enterprise\n"),
                           ("pve-enterprise.list", "deb https://enterprise.proxmox.com/debian/pve bookworm pve-enterprise\n")):
            lab.respond_seq("pve1", f"cat {D}/{name}", {"stdout": line}, {"stdout": "# " + line})
        lab.respond("pve1", f"cat {D}/pve-no-subscription.list",
                    stdout="deb http://download.proxmox.com/debian/pve bookworm pve-no-subscription\n")

    def test_yes_writes_updates_and_verifies(self):
        lab = self.lab_for("8")
        self.configured_after(lab, "Hit:1 http://download.proxmox.com/debian/pve bookworm InRelease\n")
        result = lab.run("pve-repo-setup", "pve1", "--yes")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.endswith("verify: no enterprise entry enabled: ok\n"
                                               "verify: pve-no-subscription enabled: ok\n"
                                               "verify: apt-get update without signature errors: ok\n"))
        written = {call["content"] for call in lab.calls("scp")}
        self.assertIn("deb http://download.proxmox.com/debian/pve bookworm pve-no-subscription\n", written)

    def test_signature_errors_fail(self):
        lab = self.lab_for("8")
        self.configured_after(lab, "W: GPG error: ... NO_PUBKEY 1140AF8F639E0C39\n")
        result = lab.run("pve-repo-setup", "pve1", "--yes")
        self.assertEqual(result.returncode, 1)
        self.assertIn("apt-get update reported a signature or authorization error: FAILED", result.stdout)

    def test_unsupported_version(self):
        lab = self.lab_for("8")
        lab.respond("pve1", "pveversion", stdout="pve-manager/7.4-19/f98bf8d4 (running kernel: 6.2.16-20-pve)\n")
        result = lab.run("pve-repo-setup", "pve1", "--dry-run")
        self.assertEqual(result.returncode, 1)
        self.assertIn("unsupported Proxmox VE version: pve-manager/7.4-19/f98bf8d4", result.stdout)

    def test_leftover_option_is_a_usage_error(self):
        lab = self.lab_for("8")
        result = lab.run("pve-repo-setup", "pve1", "--dryrun")
        self.assertEqual(result.returncode, 2)
        self.assertIn("unknown option: --dryrun", result.stderr)
        self.assertEqual(lab.commands("admin"), [])

    def test_without_yes_and_terminal_nothing_runs(self):
        lab = self.lab_for("8")
        result = lab.run("pve-repo-setup", "pve1")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(lab.commands("admin"), [])

    def test_a_failed_step_stops_the_tool(self):
        lab = self.lab_for("8")
        lab.respond("pve1", r"re:install -o root -g root -m 0644 /tmp/homelab-put\.[A-Za-z0-9]{8} /etc/apt/sources\.list\.d/ceph\.list",
                    exit=255, stderr="ssh: connect to host pve1-admin port 22: Broken pipe\n")
        lab.respond("pve1", RM_RE)
        result = lab.run("pve-repo-setup", "pve1", "--yes")
        self.assertEqual(result.returncode, 1)
        self.assertIn("result: exit 255\n", result.stdout)
        self.assertNotIn("verify:", result.stdout)
        self.assertEqual(len([c for c in lab.commands("admin") if "install -o root -g root -m" in c]), 1)
        self.assertFalse(any("apt-get update" in c for c in lab.commands("admin")))

    def test_unreadable_sources_list_is_not_skipped(self):
        lab = self.lab_for("8")
        lab.respond("pve1", "cat /etc/apt/sources.list", exit=255, stderr="ssh: boom\n")
        # only cat's exit 1 means "absent": any other failure fails the whole fetch
        lab.respond("pve1", f"cat {D}/ceph.list", stdout="# deb https://enterprise.proxmox.com/debian/ceph-quincy bookworm enterprise\n")
        result = lab.run("pve-repo-setup", "pve1", "--dry-run")
        self.assertEqual(result.returncode, 1)
        self.assertIn("check: cannot read the APT sources of pve1: FAILED", result.stdout)
        self.assertIn("ssh: boom", result.stderr)

    def test_missing_sources_list_is_fine_on_pve9(self):
        lab = self.lab_for("9")
        result = lab.run("pve-repo-setup", "pve1", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_failed_listing_fails(self):
        lab = self.lab_for("8")
        lab.respond("pve1", f"ls {D}", exit=255, stderr="ssh: boom\n")
        result = lab.run("pve-repo-setup", "pve1", "--dry-run")
        self.assertEqual(result.returncode, 1)
        self.assertIn("cannot read the APT sources of pve1: FAILED", result.stdout)

    def test_all_empty_sources_are_not_guessed(self):
        lab = self.lab_for("8")
        lab.respond("pve1", "cat /etc/apt/sources.list", stdout="")
        lab.respond("pve1", f"cat {D}/ceph.list", stdout="")
        lab.respond("pve1", f"cat {D}/pve-enterprise.list", stdout="")
        result = lab.run("pve-repo-setup", "pve1", "--dry-run")
        self.assertEqual(result.returncode, 1)
        self.assertIn("all empty: refusing to guess: FAILED", result.stdout)

    def test_uninterpretable_deb822_stops_before_writing(self):
        cases = {
            "crlf": ("Types: deb\r\nURIs: https://enterprise.proxmox.com/debian/pve\r\nSuites: trixie\r\n"
                     "Components: pve-enterprise\r\nEnabled: no\r\n", "has CRLF line endings"),
            "continuation": ("Types: deb\nURIs:\n https://enterprise.proxmox.com/debian/pve\nSuites: trixie\n"
                             "Components: pve-enterprise\n", "has continuation lines"),
            "nospace": ("Types: deb\nURIs: https://enterprise.proxmox.com/debian/pve\nSuites: trixie\n"
                        "Components: pve-enterprise\nEnabled:no\n", "field without a space after the colon"),
            "uris-nospace": ("Types: deb\nURIs:https://enterprise.proxmox.com/debian/pve\nSuites: trixie\n"
                             "Components:pve-enterprise\n", "field without a space after the colon"),
            "capitals": ("Types: deb\nURIs: https://ENTERPRISE.PROXMOX.COM/debian/pve\nSuites: trixie\n"
                         "Components: pve-enterprise\n", "host name with capital letters"),
        }
        for name, (text, message) in cases.items():
            with self.subTest(name):
                lab = self.lab_for("9")
                lab.respond("pve1", f"cat {D}/pve-enterprise.sources", stdout=text)
                result = lab.run("pve-repo-setup", "pve1", "--yes")
                self.assertEqual(result.returncode, 1)
                self.assertIn(message, result.stdout)
                self.assertEqual(lab.commands("admin"), [])

    def test_host_name_case_variants_stop_the_tool(self):
        cases = {
            "list": ("8", f"{D}/pve-enterprise.list",
                     "deb https://Enterprise.proxmox.com/debian/pve bookworm pve-enterprise\n"),
            "sources": ("9", f"{D}/pve-enterprise.sources",
                        "Types: deb\nURIs: https://ENTERPRISE.proxmox.com/debian/pve\nSuites: trixie\n"
                        "Components: pve-enterprise\n"),
            "download": ("8", f"{D}/pve-no-subscription.list",
                         "deb http://DOWNLOAD.proxmox.com/debian/pve bookworm pve-no-subscription\n"),
        }
        for name, (version, path, text) in cases.items():
            with self.subTest(name):
                lab = self.lab_for(version)
                if name == "download":
                    lab.respond("pve1", f"ls {D}", stdout="ceph.list\npve-enterprise.list\npve-no-subscription.list\n")
                lab.respond("pve1", f"cat {path}", stdout=text)
                result = lab.run("pve-repo-setup", "pve1", "--yes")
                self.assertEqual(result.returncode, 1)
                self.assertIn("host name with capital letters: fix it by hand first: FAILED", result.stdout)
                self.assertEqual(lab.commands("admin"), [])

    def test_trailing_comment_does_not_hide_an_enabled_entry(self):
        lab = self.lab_for("8")
        lab.respond("pve1", f"cat {D}/pve-enterprise.list",
                    stdout="deb https://enterprise.proxmox.com/debian/pve bookworm pve-enterprise # keep\n")
        result = lab.run("pve-repo-setup", "pve1", "--dry-run")
        self.assertIn(f"put {D}/pve-enterprise.list", result.stdout)
        self.assertIn("    | # deb https://enterprise.proxmox.com/debian/pve bookworm pve-enterprise # keep\n", result.stdout)

    def test_an_existing_disabled_nosub_file_is_not_overwritten(self):
        lab = self.lab_for("8")
        lab.respond("pve1", f"ls {D}", stdout="ceph.list\npve-enterprise.list\npve-no-subscription.list\n")
        lab.respond("pve1", f"cat {D}/pve-no-subscription.list",
                    stdout="# deb http://download.proxmox.com/debian/pve bookworm pve-no-subscription\n")
        result = lab.run("pve-repo-setup", "pve1", "--yes")
        self.assertEqual(result.returncode, 1)
        self.assertIn("exists but does not enable pve-no-subscription", result.stdout)
        self.assertEqual(lab.commands("admin"), [])

    def test_failed_reread_after_the_change_fails_the_verification(self):
        lab = self.lab_for("8")
        self.configured_after(lab, "Hit:1 http://download.proxmox.com/debian/pve bookworm InRelease\n")
        lab.respond_seq("pve1", f"ls {D}", {"stdout": "ceph.list\npve-enterprise.list\n"},
                        {"stdout": "", "exit": 255, "stderr": "ssh: boom\n"})
        result = lab.run("pve-repo-setup", "pve1", "--yes")
        self.assertEqual(result.returncode, 1)
        self.assertIn("verify: cannot read the APT sources of pve1: FAILED", result.stdout)

    def test_an_enterprise_entry_still_enabled_fails_the_verification(self):
        lab = self.lab_for("8")
        self.configured_after(lab, "Hit:1 http://download.proxmox.com/debian/pve bookworm InRelease\n")
        lab.respond("pve1", f"cat {D}/pve-enterprise.list",
                    stdout="deb https://enterprise.proxmox.com/debian/pve bookworm pve-enterprise\n")
        result = lab.run("pve-repo-setup", "pve1", "--yes")
        self.assertEqual(result.returncode, 1)
        self.assertIn("verify: an enterprise entry is still enabled: FAILED", result.stdout)

    def test_empty_update_output_fails(self):
        lab = self.lab_for("8")
        self.configured_after(lab, "")
        result = lab.run("pve-repo-setup", "pve1", "--yes")
        self.assertEqual(result.returncode, 1)
        self.assertIn("verify: apt-get update printed nothing: FAILED", result.stdout)

    def test_codename_must_be_present_and_match_the_version(self):
        cases = {
            "missing": ("8", 'NAME="Debian GNU/Linux"\nID=debian\n', "cannot read VERSION_CODENAME"),
            "odd": ("8", "VERSION_CODENAME=bad name1\n", "cannot read VERSION_CODENAME"),
            "mismatch": ("8", "VERSION_CODENAME=trixie\n", "Proxmox VE 8 does not match Debian trixie"),
            "mismatch9": ("9", "VERSION_CODENAME=bookworm\n", "Proxmox VE 9 does not match Debian bookworm"),
        }
        for name, (version, osrelease, message) in cases.items():
            with self.subTest(name):
                lab = self.lab_for(version)
                lab.respond("pve1", "cat /etc/os-release", stdout=osrelease)
                result = lab.run("pve-repo-setup", "pve1", "--yes")
                self.assertEqual(result.returncode, 1)
                self.assertIn(message, result.stdout)
                self.assertIn("FAILED", result.stdout)
                self.assertEqual(lab.commands("admin"), [])

    def test_other_signature_errors_fail(self):
        for text in ("W: GPG error: x\n", "EXPKEYSIG ABCD\n", "BADSIG ABCD\n"):
            with self.subTest(text):
                lab = self.lab_for("8")
                self.configured_after(lab, text)
                result = lab.run("pve-repo-setup", "pve1", "--yes")
                self.assertEqual(result.returncode, 1)
                self.assertIn("signature or authorization error: FAILED", result.stdout)


class CollectInstallTest(unittest.TestCase):
    def setUp(self):
        self.lab = Lab()
        self.addCleanup(self.lab.close)

    def test_dry_run(self):
        fx.load(self.lab)
        result = self.lab.run("pve-collect-install", "pve1", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("step 1/4: ssh pve1-admin -- install -d -o root -g root -m 0755 /etc/homelab-collect\n"
                      "step 2/4: put /usr/local/bin/homelab-collect (mode 0755) on pve1-admin\n", result.stdout)
        self.assertIn("step 4/4: put /etc/homelab-collect/local.allow (mode 0644) on pve1-admin\n", result.stdout)
        self.assertIn("baseline/after: ssh pve1 homelab-collect --version\n", result.stdout)
        self.assertEqual(self.lab.commands("admin"), [])

    def test_dry_run_summarizes_the_dispatcher_and_shows_the_lists(self):
        fx.load(self.lab)
        result = self.lab.run("pve-collect-install", "pve1", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        dispatcher = (self.lab.root / "remote" / "homelab-collect").read_bytes()
        lines = dispatcher.count(b"\n")
        digest = hashlib.sha256(dispatcher).hexdigest()[:16]
        self.assertIn("step 2/4: put /usr/local/bin/homelab-collect (mode 0755) on pve1-admin\n"
                      f"    ({lines} lines, sha256 {digest}; content not shown)\n"
                      "step 3/4: put /etc/homelab-collect/framework.allow (mode 0644) on pve1-admin\n"
                      "    | # Framework allowlist", result.stdout)
        self.assertNotIn("    | #!/usr/bin/env bash", result.stdout)

    def test_yes_installs_the_repo_files_and_verifies(self):
        self.lab.write_local("collect.allow", "pct exec 101 -- pihole -v\n")
        fx.load(self.lab)
        self.lab.install_lists(local="pct exec 101 -- pihole -v\n")
        self.lab.respond("pve1", "install -d -o root -g root -m 0755 /etc/homelab-collect")
        self.lab.respond("pve1", r"re:install -o root -g root -m 07[0-9]{2} /tmp/homelab-put\.[A-Za-z0-9]{8} /.*")
        self.lab.respond("pve1", r"re:install -o root -g root -m 0644 /tmp/homelab-put\.[A-Za-z0-9]{8} /.*")
        self.lab.respond("pve1", RM_RE)
        result = self.lab.run("pve-collect-install", "pve1", "--yes")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"verify: the dispatcher answers {fx.collect_hash(self.lab.root)}: ok\n", result.stdout)
        self.assertIn('command="/usr/local/bin/homelab-collect",restrict', result.stdout)
        copies = [call["content"] for call in self.lab.calls("scp")]
        root = self.lab.root
        self.assertEqual(copies, [(root / "remote" / "homelab-collect").read_text(),
                                  (root / "remote" / "collect.allow").read_text(),
                                  (root / "local" / "collect.allow").read_text()])

    def test_an_invalid_local_list_stops_before_anything_runs(self):
        fx.load(self.lab)
        self.lab.write_local("collect.allow", "pct exec {vmid} -- x\n")
        result = self.lab.run("pve-collect-install", "pve1", "--yes")
        self.assertEqual(result.returncode, 1)
        self.assertIn("local/collect.allow is invalid", result.stdout)
        self.assertEqual(self.lab.commands("admin"), [])

    def test_leftover_option_is_a_usage_error(self):
        fx.load(self.lab)
        result = self.lab.run("pve-collect-install", "pve1", "--dryrun")
        self.assertEqual(result.returncode, 2)
        self.assertIn("unknown option: --dryrun", result.stderr)
        self.assertEqual(self.lab.commands("admin"), [])

    def test_without_yes_and_terminal_nothing_runs(self):
        fx.load(self.lab)
        result = self.lab.run("pve-collect-install", "pve1")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.lab.commands("admin"), [])

    def test_a_failed_step_stops_the_tool(self):
        fx.load(self.lab)
        self.lab.respond("pve1", "install -d -o root -g root -m 0755 /etc/homelab-collect", exit=255, stderr="ssh: boom\n")
        result = self.lab.run("pve-collect-install", "pve1", "--yes")
        self.assertEqual(result.returncode, 1)
        self.assertIn("result: exit 255\n", result.stdout)
        self.assertNotIn("verify:", result.stdout)
        self.assertEqual(self.lab.commands("admin"), ["install -d -o root -g root -m 0755 /etc/homelab-collect"])
        self.assertEqual(self.lab.calls("scp"), [])

    def test_a_wrong_version_fails_the_verification(self):
        fx.load(self.lab)
        self.lab.respond("pve1", "install -d -o root -g root -m 0755 /etc/homelab-collect")
        self.lab.respond("pve1", r"re:install -o root -g root -m 07[0-9]{2} /tmp/homelab-put\.[A-Za-z0-9]{8} /.*")
        self.lab.respond("pve1", r"re:install -o root -g root -m 0644 /tmp/homelab-put\.[A-Za-z0-9]{8} /.*")
        self.lab.respond("pve1", RM_RE)
        self.lab.respond("pve1", "homelab-collect --version", stdout="homelab-collect 0000000000000000\n")
        result = self.lab.run("pve-collect-install", "pve1", "--yes")
        self.assertEqual(result.returncode, 1)
        self.assertIn("verify: the dispatcher answers 'homelab-collect 0000000000000000', expected", result.stdout)
        self.assertNotIn("next, by hand:", result.stdout)

    def test_an_empty_version_answer_fails_the_verification(self):
        fx.load(self.lab)
        self.lab.respond("pve1", "install -d -o root -g root -m 0755 /etc/homelab-collect")
        self.lab.respond("pve1", r"re:install -o root -g root -m 07[0-9]{2} /tmp/homelab-put\.[A-Za-z0-9]{8} /.*")
        self.lab.respond("pve1", r"re:install -o root -g root -m 0644 /tmp/homelab-put\.[A-Za-z0-9]{8} /.*")
        self.lab.respond("pve1", RM_RE)
        self.lab.respond("pve1", "homelab-collect --version", stdout="")
        result = self.lab.run("pve-collect-install", "pve1", "--yes")
        self.assertEqual(result.returncode, 1)
        self.assertIn("verify: the dispatcher answers ''", result.stdout)

    def test_an_invalid_framework_list_stops_before_anything_runs(self):
        fx.load(self.lab)
        (self.lab.root / "remote" / "collect.allow").write_text("pct exec {vmid} -- x\n")
        result = self.lab.run("pve-collect-install", "pve1", "--yes")
        self.assertEqual(result.returncode, 1)
        self.assertIn("remote/collect.allow is invalid", result.stdout)
        self.assertEqual(self.lab.commands("admin"), [])

    def test_hints_and_ownership_and_empty_local_list_warning(self):
        fx.load(self.lab)
        result = self.lab.run("pve-collect-install", "pve1", "--dry-run")
        self.assertIn("rollback: first install: remove /usr/local/bin/homelab-collect and the lists in "
                      "/etc/homelab-collect (keep use-sudo); re-install: run this tool again from the previous "
                      "commit; never remove the dispatcher while an authorized_keys line forces it\n", result.stdout)
        self.assertIn("step 1/4: ssh pve1-admin -- install -d -o root -g root -m 0755 /etc/homelab-collect\n",
                      result.stdout)
        self.assertIn("check: local/collect.allow is absent: local.allow on pve1 will be replaced by an empty "
                      "list: WARNING\n", result.stdout)
        self.lab.write_local("collect.allow", "pct exec 101 -- pihole -v\n")
        again = self.lab.run("pve-collect-install", "pve1", "--dry-run")
        self.assertNotIn("is absent", again.stdout)

    def test_a_malformed_digest_fails_before_anything_runs(self):
        fx.load(self.lab)
        fake = self.lab.base / "fakebin"
        fake.mkdir()
        (fake / "sha256sum").write_text("#!/bin/sh\ncat >/dev/null\necho 'xyz  -'\n")
        (fake / "sha256sum").chmod(0o755)
        result = self.lab.run("pve-collect-install", "pve1", "--yes",
                              PATH=f"{fake}:{self.lab.env()['PATH']}")
        self.assertEqual(result.returncode, 1)
        self.assertIn("cannot compute the version hash of the dispatcher files: FAILED", result.stdout)
        self.assertEqual(self.lab.commands("admin"), [])


if __name__ == "__main__":
    unittest.main()
