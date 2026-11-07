"""Harness for the Bash toolkit tests: a temporary repo copy, a scenario and fake ssh on PATH."""
from __future__ import annotations

import json
import os
import pty
import shutil
import subprocess
import tempfile
from pathlib import Path

from tests import ROOT

FAKES = ROOT / "tests" / "fakes"
PARTS = ("bin", "lib", "remote", "examples")


class Lab:
    """One fictional homelab per test: a repo copy with inventory, a scenario, fake ssh first on PATH."""

    def __init__(self, nodes=("pve1", "pve2"), restricted=True):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.root = self.base / "repo"
        self.root.mkdir()
        for part in PARTS:
            if (ROOT / part).exists():
                shutil.copytree(ROOT / part, self.root / part,
                                ignore=shutil.ignore_patterns("__pycache__"))
        self.etc = self.base / "etc"
        self.etc.mkdir()
        self.home = self.base / "home"
        self.home.mkdir()
        self.log = self.base / "calls.jsonl"
        self.scenario = self.base / "scenario.json"
        self.aliases: dict[str, dict] = {}
        self.responses: dict[str, dict] = {}
        for node in nodes:
            self.aliases[node] = {"role": "collect", "node": node, "restricted": restricted}
            self.aliases[f"{node}-admin"] = {"role": "admin", "node": node}
        self.write_inventory("".join(f"{node}\n" for node in nodes))
        self.install_lists()

    def close(self):
        self._tmp.cleanup()

    # -- repository content ---------------------------------------------------------------
    def write_inventory(self, text: str):
        (self.root / "inventory").mkdir(exist_ok=True)
        (self.root / "inventory" / "nodes").write_text(text, encoding="utf-8")

    def write_env(self, text: str):
        (self.root / ".env.local").write_text(text, encoding="utf-8")

    def write_local(self, rel: str, text: str, executable: bool = False) -> Path:
        path = self.root / "local" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        if executable:
            path.chmod(0o755)
        return path

    def install_lists(self, local: str = ""):
        framework = self.root / "remote" / "collect.allow"
        (self.etc / "framework.allow").write_text(
            framework.read_text() if framework.exists() else "", encoding="utf-8")
        (self.etc / "local.allow").write_text(local, encoding="utf-8")

    # -- scenario -------------------------------------------------------------------------
    def unreachable(self, alias: str):
        self.aliases[alias]["role"] = "unreachable"

    def unrestricted(self, node: str):
        self.aliases[node]["restricted"] = False

    def respond(self, node: str, command: str, stdout: str = "", exit: int = 0, stderr: str = ""):
        self.responses.setdefault(node, {})[command] = {"stdout": stdout, "exit": exit, "stderr": stderr}

    def respond_seq(self, node: str, command: str, *answers: dict):
        self.responses.setdefault(node, {})[command] = list(answers)

    def save(self):
        self.scenario.write_text(json.dumps({
            "aliases": self.aliases, "responses": self.responses,
            "dispatcher": str(self.root / "remote" / "homelab-collect"), "etc": str(self.etc),
            "log": str(self.log), "state": str(self.base / "state.json")}), encoding="utf-8")

    def env(self, **extra) -> dict:
        env = {"PATH": f"{FAKES}:{os.environ['PATH']}", "HOME": str(self.home), "LANG": "C.UTF-8",
               "LC_ALL": "C.UTF-8",
               "FAKE_SSH_SCENARIO": str(self.scenario), "HOMELAB_LOG_DIR": str(self.base / "logs")}
        env.update({key: str(value) for key, value in extra.items()})
        return env

    # -- runners --------------------------------------------------------------------------
    def run(self, tool: str, *args, stdin: str = "", **env) -> subprocess.CompletedProcess:
        self.save()
        return subprocess.run(["bash", str(self.root / "bin" / tool), *map(str, args)],
                              env=self.env(**env), cwd=self.root, input=stdin,
                              capture_output=True, text=True, timeout=120)

    def run_tty(self, argv: list, answer: str, **env) -> subprocess.CompletedProcess:
        """Run with a terminal on stdin that already holds `answer`."""
        self.save()
        master, slave = pty.openpty()
        proc = subprocess.Popen(argv, env=self.env(**env), cwd=self.root, stdin=slave,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        os.close(slave)
        os.write(master, answer.encode())
        out, err = proc.communicate(timeout=120)
        os.close(master)
        return subprocess.CompletedProcess(argv, proc.returncode, out, err)

    def shell(self, script: str, stdin: str = "", **env) -> subprocess.CompletedProcess:
        """Run Bash code from the repo root, with no library loaded."""
        self.save()
        return subprocess.run(["bash", "-c", "set -euo pipefail\n" + script], env=self.env(**env),
                              cwd=self.root, input=stdin, capture_output=True, text=True, timeout=120)

    def bash(self, script: str, stdin: str = "", **env) -> subprocess.CompletedProcess:
        """Run Bash code from the repo root with lib/pve/init.sh loaded."""
        return self.shell("source lib/pve/init.sh\n" + script, stdin=stdin, **env)

    # -- what happened --------------------------------------------------------------------
    def calls(self, tool: str = "ssh") -> list[dict]:
        if not self.log.exists():
            return []
        records = [json.loads(line) for line in self.log.read_text().splitlines()]
        return [record for record in records if record.get("tool") == tool]

    def commands(self, role: str) -> list[str]:
        return [call["command"] if role == "collect" else " ".join(call["argv"])
                for call in self.calls() if call["role"] == role]

    def audit_text(self) -> str:
        logs = self.base / "logs"
        return "".join(path.read_text() for path in sorted(logs.glob("*.log"))) if logs.exists() else ""
