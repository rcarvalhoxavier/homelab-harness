"""remote/collect.allow and the commands the tools send must match exactly."""
import re
import subprocess
import unittest
from concurrent.futures import ThreadPoolExecutor

from tests import ROOT
from tests import pvefixtures as fx
from tests.toolkit import Lab

FIELDS = {"id": r"[0-9]{1,9}", "storage": r"[A-Za-z][A-Za-z0-9_.-]{0,63}",
          "node": r"[A-Za-z0-9][A-Za-z0-9.-]*", "snap": r"[A-Za-z][A-Za-z0-9_-]{0,39}",
          "aptfile": r"/etc/apt/sources\.list\.d/[A-Za-z0-9_.-]+\.(list|sources)"}
PROBES = {"id", "homelab-collect --version"}   # sent on purpose: the restriction probe, the version query

RUNS = [
    ("pve-state", "101"), ("pve-state", "200"), ("pve-state", "pve1"),
    ("pve-health", "--today", "2026-07-01"), ("pve-capacity",), ("pve-selftest",),
    ("pve-snapshot", "101", "x1", "--dry-run"), ("pve-backup", "101", "--dry-run"),
    ("pve-update-host", "pve1", "--dry-run"), ("pve-update-host", "pve1", "--simulate"),
    ("pve-update-ct", "101", "--snapshot", "--dry-run"), ("pve-cleanup", "pve1", "--dry-run"),
    ("pve-move-disk", "200", "fast", "--dry-run"), ("pve-repo-setup", "pve1", "--dry-run"),
    ("pve-collect-install", "pve1", "--dry-run"),
    ("pve-discover",), ("pve-discover", "--seed", "pve1"),
    # confirmed runs, so the verification reads are sent too
    ("pve-update-host", "pve1", "--yes"), ("pve-cleanup", "pve1", "--yes"), ("pve-snapshot", "101", "x1", "--yes"),
]


# a storage that accepts guest disks, so pve-move-disk runs every check
FAST_STATUS = "fast           lvmthin     active       500000000        10000000       490000000    2.00%\n"
FAST_CFG = "\nlvmthin: fast\n\tthinpool fast\n\tvgname ssd\n\tcontent rootdir,images\n"


def prepare(lab: Lab, run: tuple) -> None:
    """Answers that let a confirmed run reach its verification reads and succeed."""
    if "--seed" in run:
        (lab.root / "inventory" / "nodes").unlink()   # onboarding runs before the inventory exists
    if run[:3] == ("pve-update-host", "pve1", "--yes"):
        lab.respond_seq("pve1", "apt-get -s dist-upgrade", fx.ok(fx.APT_SIM), fx.ok(fx.APT_SIM),
                        fx.ok(fx.APT_SIM_NONE))
    if run[0] == "pve-snapshot" and "--yes" in run:
        listed = fx.SNAPSHOTS["101"].replace(" `-> current", " `-> x1                          2026-07-01 09:00:00     no-description\n"
                                             "    `-> current")
        lab.respond_seq("pve1", "pct listsnapshot 101", fx.ok(fx.SNAPSHOTS["101"]), fx.ok(listed))


def rules() -> list[str]:
    lines = (ROOT / "remote" / "collect.allow").read_text().splitlines()
    return [line for line in lines if line.strip() and not line.lstrip().startswith("#")]


def matches(rule: str, command: str) -> bool:
    pattern, argv = rule.split(" "), command.split(" ")
    if len(pattern) != len(argv):
        return False
    for want, got in zip(pattern, argv):
        field = re.fullmatch(r"\{([a-z]+)\}", want)
        if field:
            if not re.fullmatch(FIELDS[field.group(1)], got):
                return False
        elif want != got:
            return False
    return True


class ContractTest(unittest.TestCase):
    @staticmethod
    def _drive(version, ghost, run):
        """One tool run in its own lab (runs are independent, so they can go in parallel)."""
        lab = Lab()
        try:
            fx.load(lab, version)
            lab.write_env("PVE_BACKUP_STORAGE=nas-backup\n")
            for node in ("pve1", "pve2"):
                lab.respond(node, "re:.*")          # any command without a fixture answers empty
                lab.responses[node]["pvesm status"]["stdout"] += FAST_STATUS
                lab.responses[node]["cat /etc/pve/storage.cfg"]["stdout"] += FAST_CFG
                if ghost:
                    status = lab.responses[node]["pvecm status"]["stdout"]
                    lab.respond(node, "pvecm status",
                                stdout=status.replace("Expected votes:   2", "Expected votes:   3"))
                    lab.respond(node, "ls /etc/pve/nodes", stdout="pve1\npve2\npve3\n")
            prepare(lab, run)
            result = lab.run(*run)
            collect = [call for call in lab.calls() if call["role"] == "collect"]
            return ({call["command"] for call in collect},
                    {call["command"] for call in collect if call["refused"]},
                    (version, ghost, run, result.returncode, result.stdout[-300:] + result.stderr[-300:]))
        finally:
            lab.close()

    @classmethod
    def setUpClass(cls):
        cls.sent, cls.refused, cls.results = set(), set(), []
        jobs = [(v, False, run) for v in ("8", "9") for run in RUNS] + [("8", True, ("pve-capacity",))]
        with ThreadPoolExecutor(max_workers=8) as pool:
            for sent, refused, outcome in pool.map(lambda job: cls._drive(*job), jobs):
                cls.sent |= sent
                cls.refused |= refused
                cls.results.append(outcome)

    def test_every_run_completes(self):
        # a run that stops early (a failed check) would leave its later reads untested
        failed = [outcome for outcome in self.results if outcome[3] != 0]
        self.assertEqual(failed, [])

    def test_no_tool_was_refused(self):
        self.assertEqual(sorted(self.refused - PROBES), [])

    def test_every_command_sent_is_on_the_list(self):
        self.assertEqual(sorted(c for c in self.sent - PROBES if not any(matches(r, c) for r in rules())), [])

    def test_every_line_of_the_list_is_used(self):
        self.assertEqual([r for r in rules() if not any(matches(r, c) for c in self.sent)], [])

    def test_the_python_matcher_agrees_with_the_dispatcher(self):
        lab = Lab()
        self.addCleanup(lab.close)
        for command in sorted(self.sent | {"pct config 101x", "cat /etc/shadow", "pct list; id"}):
            with self.subTest(command=command):
                verdict = subprocess.run(["bash", str(ROOT / "remote" / "homelab-collect"), "--etc", str(lab.etc),
                                          "--match", command], capture_output=True, text=True).stdout.strip()
                expected = command in PROBES - {"id"} or any(matches(r, command) for r in rules())
                self.assertEqual(verdict, "allowed" if expected else "refused")


if __name__ == "__main__":
    unittest.main()
