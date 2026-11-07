"""bin/init: create the instance wiki from templates/wiki/ without overwriting anything."""
from __future__ import annotations

import argparse
import datetime
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable

from .config import WIKI_DIRS
from .util import harness_root

CHOICES = {"mode": ("personal", "team"), "exposure": ("private", "public"), "language": None}
DEFAULTS = {"mode": "personal", "exposure": "private", "language": "en"}


def ask(key: str, input_fn: Callable[[str], str]) -> str:
    choices = CHOICES[key]
    hint = f" ({'/'.join(choices)})" if choices else ""
    while True:
        try:
            answer = input_fn(f"{key}{hint} [{DEFAULTS[key]}]: ").strip()
        except EOFError:
            return DEFAULTS[key]
        answer = answer or DEFAULTS[key]
        if choices is None or answer in choices:
            return answer
        print(f"  {key} must be one of: {', '.join(choices)}")


LANGUAGE_RE = re.compile(r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$")


def language(value: str) -> str:
    if not LANGUAGE_RE.match(value):
        raise argparse.ArgumentTypeError(f"not a language tag like en, pt-BR or es-419: {value!r}")
    return value


def render(text: str, values: dict[str, str]) -> str:
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    return text


def earlier_hooks(root: Path) -> set[bytes]:
    """Every committed version of the hook template: an installed copy of one of them is ours to
    replace after an upstream merge changed the hook; anything else is the user's."""
    path = "templates/hooks/pre-commit"
    try:
        commits = subprocess.run(["git", "-C", str(root), "log", "--format=%H", "--", path],
                                 capture_output=True, text=True, check=True).stdout.split()
    except (OSError, subprocess.CalledProcessError):
        return set()
    versions = set()
    for commit in commits:
        # the commit that deleted the file has no version of it
        shown = subprocess.run(["git", "-C", str(root), "show", f"{commit}:{path}"], capture_output=True)
        if shown.returncode == 0:
            versions.add(shown.stdout)
    return versions


def install_hook(root: Path) -> int:
    try:
        out = subprocess.run(["git", "-C", str(root), "rev-parse", "--absolute-git-dir", "--git-path", "hooks"],
                             capture_output=True, text=True, check=True).stdout.split("\n")
    except (OSError, subprocess.CalledProcessError):
        print("hooks: not a git repository; hook not installed", file=sys.stderr)
        return 1
    git_dir, hooks = Path(out[0].strip()), out[1].strip()
    hooks_dir = Path(hooks) if Path(hooks).is_absolute() else root / hooks
    source = root / "templates" / "hooks" / "pre-commit"
    if not hooks_dir.resolve().is_relative_to(git_dir.resolve()):
        # core.hooksPath points elsewhere (a hooks manager, dotfiles): a hook written there
        # would run in every repository that shares it.
        print(f"hooks: core.hooksPath points outside this repository ({hooks_dir}); not installing.\n"
              f"  Call this script from your hooks manager instead: {source}", file=sys.stderr)
        return 1
    dest = hooks_dir / "pre-commit"
    if dest.exists():
        if dest.read_bytes() == source.read_bytes():
            print(f"exists: {dest}")
            return 0
        if dest.read_bytes() in earlier_hooks(root):
            shutil.copyfile(source, dest)
            dest.chmod(0o755)
            print(f"updated: {dest}")
            return 0
        print(f"hooks: {dest} already exists and differs; left untouched.\n"
              f"  To add the wiki secret check, call this from your hook: {source}",
              file=sys.stderr)
        return 1
    hooks_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, dest)
    dest.chmod(0o755)
    print(f"created: {dest}")
    return 0


def main(argv: list[str] | None = None, input_fn: Callable[[str], str] = input) -> int:
    parser = argparse.ArgumentParser(
        prog="init", description="Create wiki/ from templates/wiki/. Never overwrites existing files.")
    parser.add_argument("--mode", choices=CHOICES["mode"])
    parser.add_argument("--exposure", choices=CHOICES["exposure"])
    parser.add_argument("--language", type=language, help="language tag of the wiki pages, e.g. en, pt-BR")
    parser.add_argument("--hooks", action="store_true", help="install the pre-commit secret check")
    parser.add_argument("--non-interactive", action="store_true",
                        help="use defaults instead of prompting")
    parser.add_argument("--root", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    root = (args.root or harness_root()).resolve()
    templates = root / "templates" / "wiki"
    wiki = root / "wiki"
    values = {"date": datetime.date.today().isoformat()}
    if not (wiki / "AGENTS.md").exists():
        for key in ("mode", "exposure", "language"):
            given = getattr(args, key)
            if given:
                values[key] = given
            elif args.non_interactive:
                values[key] = DEFAULTS[key]
            else:
                values[key] = ask(key, input_fn)

    created, existing = [], []
    for source in sorted(templates.rglob("*")):
        if not source.is_file():
            continue
        dest = wiki / source.relative_to(templates)
        if dest.exists():
            existing.append(dest)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(render(source.read_text(encoding="utf-8"), values), encoding="utf-8")
        created.append(dest)
    # Instance rules outside wiki/: auto-loaded by Claude Code, never shipped by upstream.
    rules_source = root / "templates" / "rules" / "local.md"
    rules_dest = root / ".claude" / "rules" / "local.md"
    if rules_source.is_file():
        if rules_dest.exists():
            existing.append(rules_dest)
        else:
            rules_dest.parent.mkdir(parents=True, exist_ok=True)
            rules_dest.write_text(rules_source.read_text(encoding="utf-8"), encoding="utf-8")
            created.append(rules_dest)
    for name in WIKI_DIRS:
        directory = wiki / name
        directory.mkdir(parents=True, exist_ok=True)
        keep = directory / ".gitkeep"
        if not keep.exists() and not any(directory.iterdir()):
            keep.touch()
            created.append(keep)

    for path in created:
        print(f"created: {path.relative_to(root).as_posix()}")
    for path in existing:
        print(f"exists:  {path.relative_to(root).as_posix()}")
    status = install_hook(root) if args.hooks else 0
    if created:
        print("\nNext: fill the [CUSTOMIZE] sections of wiki/AGENTS.md, then capture evidence:\n"
              '  <command> | bin/wiki-capture <slug> --origin "<command> @ <host>"')
    return status
