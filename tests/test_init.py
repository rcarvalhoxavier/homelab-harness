import io
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from tests.helpers import GIT_ENV, copy_harness
from wikitools import init
from wikitools.config import load_config


def quiet(fn, *args, **kwargs):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = fn(*args, **kwargs)
    return code, out.getvalue(), err.getvalue()


class InitTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = copy_harness(Path(self.tmp.name))
        patcher = mock.patch.dict(os.environ, GIT_ENV)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def run_init(self, *args, input_fn=None):
        return quiet(init.main, ["--root", str(self.root), *args],
                     input_fn=input_fn or (lambda prompt: ""))

    def test_fresh_wiki_with_defaults(self):
        code, out, _ = self.run_init("--non-interactive")
        self.assertEqual(code, 0)
        wiki = self.root / "wiki"
        cfg = load_config(wiki)
        self.assertEqual((cfg.mode, cfg.exposure, cfg.language), ("personal", "private", "en"))
        for name in ("index.md", "log.md", "overview.md", ".capture-patterns"):
            self.assertTrue((wiki / name).is_file(), name)
        for name in ("raw", "entities", "concepts", "sources", "changes", "analyses"):
            self.assertTrue((wiki / name / ".gitkeep").is_file(), name)
        self.assertRegex((wiki / "log.md").read_text(),
                         r"## \[\d{4}-\d{2}-\d{2}\] update \| Wiki created")
        self.assertNotIn("{{", (wiki / "AGENTS.md").read_text())
        self.assertIn("created: wiki/AGENTS.md", out)

    def test_explicit_values(self):
        self.run_init("--mode", "team", "--exposure", "public", "--language", "pt-BR",
                      "--non-interactive")
        cfg = load_config(self.root / "wiki")
        self.assertEqual((cfg.mode, cfg.exposure, cfg.language), ("team", "public", "pt-BR"))

    def test_prompts_and_reprompts_on_invalid_answer(self):
        answers = iter(["solo", "team", "public", "pt"])
        _, out, _ = self.run_init(input_fn=lambda prompt: next(answers))
        cfg = load_config(self.root / "wiki")
        self.assertEqual((cfg.mode, cfg.exposure, cfg.language), ("team", "public", "pt"))
        self.assertIn("mode must be one of", out)

    def test_second_run_changes_nothing(self):
        self.run_init("--non-interactive")
        snapshot = lambda: {p: p.read_bytes() for p in (self.root / "wiki").rglob("*") if p.is_file()}
        before = snapshot()
        _, out, _ = self.run_init("--non-interactive")
        self.assertEqual(snapshot(), before)
        self.assertNotIn("created:", out)
        self.assertIn("exists:", out)

    def test_never_overwrites_and_restores_missing(self):
        self.run_init("--non-interactive")
        index = self.root / "wiki" / "index.md"
        index.write_text("# mine\n")
        (self.root / "wiki" / "overview.md").unlink()
        _, out, _ = self.run_init("--non-interactive")
        self.assertEqual(index.read_text(), "# mine\n")
        self.assertTrue((self.root / "wiki" / "overview.md").is_file())
        self.assertIn("created: wiki/overview.md", out)

    def git_init(self):
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)

    def test_hook_installed_once(self):
        self.git_init()
        code, _, _ = self.run_init("--non-interactive", "--hooks")
        hook = self.root / ".git" / "hooks" / "pre-commit"
        self.assertEqual(code, 0)
        self.assertTrue(os.access(hook, os.X_OK))
        self.assertEqual(hook.read_bytes(),
                         (self.root / "templates" / "hooks" / "pre-commit").read_bytes())
        code, out, _ = self.run_init("--non-interactive", "--hooks")
        self.assertEqual(code, 0)
        self.assertIn("exists:", out)

    def test_hook_refuses_to_replace_a_foreign_hook(self):
        self.git_init()
        hook = self.root / ".git" / "hooks" / "pre-commit"
        hook.parent.mkdir(parents=True, exist_ok=True)
        hook.write_text("#!/bin/sh\necho mine\n")
        code, _, err = self.run_init("--non-interactive", "--hooks")
        self.assertEqual(code, 1)
        self.assertEqual(hook.read_text(), "#!/bin/sh\necho mine\n")
        self.assertIn("already exists", err)

    def test_hook_replaces_an_earlier_version_of_the_template(self):
        # an instance that ran --hooks before an upstream merge changed the hook
        self.git_init()
        source = self.root / "templates" / "hooks" / "pre-commit"
        current = source.read_bytes()
        old = b"#!/usr/bin/env bash\n# an earlier hook\nexit 0\n"
        git = ["git", "-C", str(self.root), "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
        source.write_bytes(old)
        subprocess.run([*git, "add", "templates/hooks/pre-commit"], check=True)
        subprocess.run([*git, "commit", "-q", "-m", "old hook"], check=True)
        source.write_bytes(current)
        subprocess.run([*git, "commit", "-q", "-am", "new hook"], check=True)
        hook = self.root / ".git" / "hooks" / "pre-commit"
        hook.parent.mkdir(parents=True, exist_ok=True)
        hook.write_bytes(old)
        code, out, err = self.run_init("--non-interactive", "--hooks")
        self.assertEqual(code, 0, err)
        self.assertEqual(hook.read_bytes(), current)
        self.assertTrue(os.access(hook, os.X_OK))
        self.assertIn("updated:", out)

    def test_hook_outside_git(self):
        code, _, err = self.run_init("--non-interactive", "--hooks")
        self.assertEqual(code, 1)
        self.assertIn("not a git repository", err)


if __name__ == "__main__":
    unittest.main()
