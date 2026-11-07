"""Shared test helpers."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

from tests import ROOT

AGENTS_TEMPLATE = """\
---
harness_schema: 1
mode: personal
exposure: {exposure}
language: en
stale_after_days: 90
pending_after_days: 14
extra_trust_levels: [{extra_trust}]
extra_entity_kinds: [{extra_kinds}]
---

# Test wiki schema
"""

# Isolates git from the developer's global/system config (hooksPath, signing, ...).
GIT_ENV = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}


def write_files(base: Path, files: dict) -> None:
    """Write {relative path: str | bytes}. str content is dedented."""
    for rel, content in files.items():
        path = Path(base) / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(textwrap.dedent(content), encoding="utf-8")


def make_wiki(base: Path, files: dict | None = None, exposure: str = "private",
              extra_trust: str = "", extra_kinds: str = "") -> Path:
    wiki = Path(base) / "wiki"
    write_files(wiki, {"AGENTS.md": AGENTS_TEMPLATE.format(
        exposure=exposure, extra_trust=extra_trust, extra_kinds=extra_kinds)})
    write_files(wiki, files or {})
    return wiki


def run_bin(name: str, *args, stdin: str | None = None,
            cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(ROOT / "bin" / name), *map(str, args)],
                          input=stdin, capture_output=True, text=True, cwd=cwd)


def copy_harness(dest: Path) -> Path:
    """Copy the framework parts a fresh checkout has (bin, lib, templates)."""
    for part in ("bin", "lib", "templates"):
        if (ROOT / part).exists():
            shutil.copytree(ROOT / part, Path(dest) / part,
                            ignore=shutil.ignore_patterns("__pycache__"))
    return Path(dest)


RAW_NODE = b"pve-manager/8.4.1\nuptime 12 days\n"


def clean_wiki(base: Path, exposure: str = "private", extra_trust: str = "",
               extra_kinds: str = "") -> Path:
    """A minimal wiki that must produce zero findings in every lint task."""
    from wikitools.util import short_hash
    return make_wiki(base, {
        "raw/2026-06-01-node-status.txt": RAW_NODE,
        "sources/2026-06-01-node-status.md": f"""\
            ---
            title: Node status
            date: 2026-06-01
            type: measurement
            source: raw/2026-06-01-node-status.txt
            source_hash: {short_hash(RAW_NODE)}
            trust_level: measured
            ---

            ## Summary

            Version and uptime of [[entities/host-pve1]].
            """,
        "entities/host-pve1.md": """\
            ---
            kind: host
            status: active
            last_verified: 2026-06-01
            ---

            # host-pve1

            Proxmox node running pve-manager 8.4.1 [[sources/2026-06-01-node-status]].
            """,
        "index.md": """\
            # Index

            - [[entities/host-pve1]] — the node
            - [[sources/2026-06-01-node-status]] — node status
            """,
        "log.md": """\
            # Log

            ## [2026-06-01] ingest | Node status
            """,
        "overview.md": """\
            # Overview

            One node: [[entities/host-pve1]].
            """,
    }, exposure=exposure, extra_trust=extra_trust, extra_kinds=extra_kinds)


def lint(wiki: Path, today: str = "2026-07-01", env_file: Path | None = None):
    import datetime
    from wikitools.lint import Linter
    return Linter(wiki, datetime.date.fromisoformat(today), env_file).run()


def codes(findings) -> list[tuple[str, str]]:
    return [(f.code, f.path) for f in findings]


def append(path: Path, text: str) -> None:
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(text)
