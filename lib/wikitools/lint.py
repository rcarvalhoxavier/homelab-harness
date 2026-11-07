"""wiki-lint: deterministic health checks for an llm-wiki.

Everything a machine can decide lives here, so it runs the same way in the
skill, in CI and in the pre-commit hook. The LLM keeps only the semantic lint
(duplicates, superseded claims, missing concept pages).
"""
from __future__ import annotations

import argparse
import datetime
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from . import frontmatter, markdown, redact
from .encoding import EncodingError, decode
from .config import (CHANGE_OUTCOMES, CHANGE_ROLLBACKS, ENTITY_STATUSES, LOG_OPS, PAGE_DIRS,
                     SOURCE_REQUIRED, SOURCE_TYPES, ConfigError, WikiConfig, load_config)
from .util import harness_root, parse_date, repo_root_for, short_hash

LEVEL_ORDER = {"ERROR": 0, "WARN": 1, "INFO": 2}
LOG_HEADING_RE = re.compile(r"^## \[\d{4}-\d{2}-\d{2}\] (?:" + "|".join(LOG_OPS) + r") \| \S.*$")
HASH_RE = re.compile(r"^[0-9a-f]{16}$")
ALLOW_FILE = ".secret-scan-allow"
SCAN_SKIP = {".capture-patterns", ".gitkeep", ALLOW_FILE}
URL_RE = re.compile(r"^[a-z][a-z0-9+.-]*://", re.IGNORECASE)
CONTRADICTION_RE = re.compile(r"^#{2,6}\s*(?:⚠️?\s*)?contrad", re.IGNORECASE)
PENDING_HEADING_RE = re.compile(r"^#{2,6}\s+pend", re.IGNORECASE)
UNCHECKED_RE = re.compile(r"^\s*[-*]\s+\[ \]\s+(.*)$")
CITATION_RE = re.compile(r"\[\[(?:sources|changes)/")
UNCITED_MIN_WORDS = 12


@dataclass(frozen=True)
class Finding:
    level: str     # ERROR | WARN | INFO
    path: str      # relative to the wiki root, or absolute for files outside it
    line: int
    code: str
    message: str

    def format(self, prefix: str) -> str:
        shown = self.path if self.path.startswith("/") else prefix + self.path
        return f"{self.level} {shown}:{self.line} {self.code} {self.message}"


@dataclass(frozen=True)
class Allow:
    """One reviewed exception of the secret scan: this rule may fire on the line with this hash."""
    line: int      # line of the entry in the allow file
    path: str      # relative to the repository root
    digest: str    # short_hash of the line's text
    rule: str


def load_allow(path: Path) -> tuple[list[Allow], list[tuple[int, str]]]:
    """Read an allow file: `<path> <line hash> <rule>  # <reason>` per line. Returns the entries
    and the (line, message) errors; a missing file has neither."""
    entries, errors = [], []
    if not path.is_file():
        return entries, errors
    for number, raw in enumerate(path.read_text(encoding="utf-8").split("\n"), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        entry, _, reason = line.partition("#")
        fields = entry.split()
        if len(fields) != 3 or not HASH_RE.match(fields[1]):
            errors.append((number, "an exception is `<path> <16-hex line hash> <rule>  # <reason>`"))
        elif not reason.strip():
            errors.append((number, "an exception needs a reason after #: who reviewed it and why it "
                                   "is not a secret"))
        else:
            entries.append(Allow(number, fields[0], fields[1], fields[2]))
    return entries, errors


@dataclass
class Doc:
    rel: str
    text: str
    meta: dict | None
    meta_error: str | None
    body: str
    body_line: int

    def key_line(self, key: str) -> int:
        """File line of `key:` inside the frontmatter, or 1."""
        for number, line in enumerate(self.text.split("\n")[: self.body_line], 1):
            if line.startswith(f"{key}:"):
                return number
        return 1


def load_doc(wiki: Path, path: Path) -> Doc:
    text = path.read_text(encoding="utf-8", errors="replace")
    fm, body, body_line = frontmatter.split(text)
    meta, error = None, None
    if fm is not None:
        try:
            meta = frontmatter.parse(fm)
        except frontmatter.FrontmatterError as exc:
            error = f"invalid frontmatter: {exc}"
    return Doc(path.relative_to(wiki).as_posix(), text, meta, error, body, body_line)


def _is_utf8(data: bytes) -> bool:
    try:
        data.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def _ref_rel(ref: str) -> str:
    return f"{ref.removesuffix('.md')}.md"


class Linter:
    CHECKS: tuple[str, ...] = ("check_links", "check_log", "check_sources", "check_entities",
                               "check_changes", "check_contradictions", "check_uncited",
                               "check_secrets", "check_frontmatter", "check_schema")

    def __init__(self, wiki: Path, today: datetime.date, env_file: Path | None = None,
                 allow_file: Path | None = None, paths_root: Path | None = None):
        self.wiki = Path(wiki).resolve()
        self.today = today
        self.findings: list[Finding] = []
        self.repo = repo_root_for(self.wiki)
        self.paths_root = Path(paths_root).resolve() if paths_root else None
        self.allow_file = Path(allow_file) if allow_file else self.wiki / ALLOW_FILE
        self.allowed = 0                                   # findings an exception suppressed
        self.candidates: list[tuple[str, str, str]] = []   # (path, line hash, rule) not allowed
        self.allow, errors = load_allow(self.allow_file)
        for number, message in errors:
            self.add("ERROR", ALLOW_FILE, number, "E-CONFIG", message)
        try:
            self.config = load_config(self.wiki)
        except ConfigError as exc:
            self.config = WikiConfig()
            self.add("ERROR", "AGENTS.md", exc.line, "E-CONFIG", str(exc))
        try:
            custom = redact.load_custom_patterns(self.wiki / ".capture-patterns")
        except redact.PatternError as exc:
            custom = []
            self.add("ERROR", ".capture-patterns", exc.line, "E-CONFIG", str(exc))
        self.secret_rules = redact.build_rules(redact.load_env_literals(env_file), custom, "private")
        self.exposure_rules = list(redact.EXPOSURE_RULES) if self.config.exposure == "public" else []

    def add(self, level: str, path: str, line: int, code: str, message: str) -> None:
        self.findings.append(Finding(level, path, line, code, message))

    def files(self) -> list[Path]:
        """Every file of the wiki except dotfiles (.capture-patterns, .gitkeep, ...)."""
        found = []
        for path in sorted(self.wiki.rglob("*")):
            if path.is_file() and not any(part.startswith(".")
                                          for part in path.relative_to(self.wiki).parts):
                found.append(path)
        return found

    def secret_files(self) -> list[Path]:
        """Every file the secret scan reads: dot-directories too (an Obsidian plugin keeps API
        keys in wiki/.obsidian/), except the patterns file, which matches its own regexes."""
        return [path for path in sorted(self.wiki.rglob("*"))
                if path.is_file() and path.name not in SCAN_SKIP]

    def docs(self) -> dict[str, Doc]:
        """Markdown documents outside raw/ (raw/ holds evidence, even when it is .md)."""
        return {
            path.relative_to(self.wiki).as_posix(): load_doc(self.wiki, path)
            for path in self.files()
            if path.suffix == ".md" and path.relative_to(self.wiki).parts[0] != "raw"
        }

    def inside(self, path: Path, root: Path | None = None) -> bool:
        return path.resolve().is_relative_to((root or self.wiki).resolve())

    def page_exists(self, ref) -> bool:
        if not isinstance(ref, str) or not ref:
            return False
        path = self.wiki / _ref_rel(ref)
        return self.inside(path) and path.is_file()

    def run(self) -> list[Finding]:
        docs = self.docs()
        for name in self.CHECKS:
            getattr(self, name)(docs)
        return self.sorted_findings()

    def sorted_findings(self) -> list[Finding]:
        return sorted(set(self.findings),
                      key=lambda f: (LEVEL_ORDER[f.level], f.path, f.line, f.code, f.message))

    def check_links(self, docs: dict[str, Doc]) -> None:
        pages = {rel for rel in docs if rel.split("/")[0] in PAGE_DIRS}
        inbound: dict[str, set[str]] = {rel: set() for rel in pages}
        indexed: set[str] = set()
        for rel, doc in docs.items():
            for line, target in markdown.wikilinks(doc.text):
                target_rel = _ref_rel(target)
                if not self.inside(self.wiki / target_rel):
                    self.add("ERROR", rel, line, "E-LINK", f"[[{target}]] points outside the wiki")
                elif not (self.wiki / target_rel).is_file():
                    self.add("ERROR", rel, line, "E-LINK", f"[[{target}]] does not exist")
                elif rel == "index.md":
                    indexed.add(target_rel)
                elif rel != "log.md" and target_rel in inbound and target_rel != rel:
                    inbound[target_rel].add(rel)
            if rel.startswith("changes/") and doc.meta:
                targets = doc.meta.get("targets")
                refs = list(targets) if isinstance(targets, list) else []
                refs += [doc.meta.get("baseline"), doc.meta.get("after")]
                for ref in refs:
                    if self.page_exists(ref) and _ref_rel(ref) in inbound and _ref_rel(ref) != rel:
                        inbound[_ref_rel(ref)].add(rel)
        for rel in sorted(pages):
            if not inbound[rel]:
                self.add("WARN", rel, 1, "W-ORPHAN", "no other page links here")
            if rel not in indexed:
                self.add("WARN", rel, 1, "W-INDEX", "not listed in index.md")

    def check_log(self, docs: dict[str, Doc]) -> None:
        doc = docs.get("log.md")
        if doc is None:
            return
        prose, _ = markdown.split_code(doc.text)
        for number, line in enumerate(prose.split("\n"), 1):
            if line.startswith("## ") and not LOG_HEADING_RE.match(line.rstrip()):
                self.add("WARN", "log.md", number, "W-LOG",
                         "heading must be '## [YYYY-MM-DD] <op> | <title>' with op one of "
                         + ", ".join(LOG_OPS))

    def check_sources(self, docs: dict[str, Doc]) -> None:
        cited_raw: set[str] = set()
        repo = repo_root_for(self.wiki)
        for rel, doc in docs.items():
            if not rel.startswith("sources/"):
                continue
            if "TODO(ingest)" in doc.text:
                line = doc.text[: doc.text.index("TODO(ingest)")].count("\n") + 1
                self.add("WARN", rel, line, "W-STUB", "still has TODO(ingest): finish the ingest")
            meta = doc.meta
            if meta is None:
                self.add("ERROR", rel, 1, "E-SRC-FIELD", doc.meta_error or "missing frontmatter")
                continue
            for key in SOURCE_REQUIRED:
                if meta.get(key) in (None, ""):
                    self.add("ERROR", rel, 1, "E-SRC-FIELD", f"missing required field: {key}")
            if meta.get("date") not in (None, "") and parse_date(meta["date"]) is None:
                self.add("ERROR", rel, doc.key_line("date"), "E-SRC-FIELD",
                         f"date must be YYYY-MM-DD (got {meta['date']!r})")
            if meta.get("type") not in (None, "") and meta["type"] not in SOURCE_TYPES:
                self.add("ERROR", rel, doc.key_line("type"), "E-SRC-FIELD",
                         f"type must be one of: {', '.join(SOURCE_TYPES)} (got {meta['type']!r})")
            digest = meta.get("source_hash")
            if digest not in (None, "") and not (isinstance(digest, str) and HASH_RE.match(digest)):
                self.add("ERROR", rel, doc.key_line("source_hash"), "E-SRC-FIELD",
                         "source_hash must be 16 lowercase hex characters (quote it if all digits)")
                digest = None
            trust = meta.get("trust_level")
            if trust not in (None, "") and trust not in self.config.trust_levels:
                self.add("ERROR", rel, doc.key_line("trust_level"), "E-TRUST",
                         f"unknown trust_level {trust!r}; declare local tiers in extra_trust_levels")
            source = meta.get("source")
            if not isinstance(source, str) or not source:
                continue
            if URL_RE.match(source):
                self.add("ERROR", rel, doc.key_line("source"), "E-SRC-FIELD",
                         "source must be a raw/ or repo path; save the page to raw/ and keep the URL in url:")
                continue
            is_raw = source.startswith("raw/")
            target = (self.wiki if is_raw else repo) / source
            if not self.inside(target, self.wiki / "raw" if is_raw else repo):
                self.add("ERROR", rel, doc.key_line("source"), "E-SRC-FIELD",
                         f"{source} points outside {'raw/' if is_raw else 'the repository'}")
                continue
            if is_raw:
                cited_raw.add(source)
            if not target.is_file():
                self.add("ERROR", rel, doc.key_line("source"), "E-SRC-MISSING", f"{source} does not exist")
                continue
            if not isinstance(digest, str) or not digest:
                continue
            actual = short_hash(target.read_bytes())
            if actual == digest:
                continue
            if is_raw:
                self.add("ERROR", rel, doc.key_line("source_hash"), "E-RAW-HASH",
                         f"{source} hashes to {actual} but source_hash is {digest}: "
                         "evidence under raw/ must never change")
            else:
                self.add("WARN", rel, doc.key_line("source_hash"), "W-REPO-HASH",
                         f"{source} changed since ingest ({digest} -> {actual}); reingest it")
        for path in self.files():
            rel = path.relative_to(self.wiki).as_posix()
            if rel.startswith("raw/") and rel not in cited_raw:
                self.add("WARN", rel, 1, "W-RAW-UNCITED", "no source page cites this file")

    def check_entities(self, docs: dict[str, Doc]) -> None:
        kinds = self.config.entity_kinds
        for rel, doc in docs.items():
            if not rel.startswith("entities/"):
                continue
            meta = doc.meta
            if meta is None:
                self.add("ERROR", rel, 1, "E-ENTITY-FIELD",
                         doc.meta_error or "missing frontmatter (kind, status)")
                continue
            if meta.get("kind") not in kinds:
                self.add("ERROR", rel, doc.key_line("kind"), "E-ENTITY-FIELD",
                         f"kind must be one of: {', '.join(kinds)} (got {meta.get('kind')!r})")
            if meta.get("status") not in ENTITY_STATUSES:
                self.add("ERROR", rel, doc.key_line("status"), "E-ENTITY-FIELD",
                         f"status must be one of: {', '.join(ENTITY_STATUSES)} (got {meta.get('status')!r})")
            if "last_verified" not in meta:
                continue
            verified = parse_date(meta["last_verified"])
            if verified is None:
                self.add("ERROR", rel, doc.key_line("last_verified"), "E-ENTITY-FIELD",
                         f"last_verified must be YYYY-MM-DD (got {meta['last_verified']!r})")
                continue
            age = (self.today - verified).days
            if age > self.config.stale_after_days:
                self.add("WARN", rel, doc.key_line("last_verified"), "W-STALE",
                         f"last verified {meta['last_verified']} ({age} days ago, limit "
                         f"{self.config.stale_after_days}); capture its state again")

    def check_changes(self, docs: dict[str, Doc]) -> None:
        limit = self.config.pending_after_days
        for rel, doc in docs.items():
            if not rel.startswith("changes/"):
                continue
            meta = doc.meta
            if meta is None:
                self.add("ERROR", rel, 1, "E-CHANGE-FIELD", doc.meta_error or "missing frontmatter")
                continue
            date = parse_date(meta.get("date"))
            if date is None:
                self.add("ERROR", rel, doc.key_line("date"), "E-CHANGE-FIELD",
                         f"date must be YYYY-MM-DD (got {meta.get('date')!r})")
            outcome = meta.get("outcome")
            if outcome not in CHANGE_OUTCOMES:
                self.add("ERROR", rel, doc.key_line("outcome"), "E-CHANGE-FIELD",
                         f"outcome must be one of: {', '.join(CHANGE_OUTCOMES)} (got {outcome!r})")
            if meta.get("rollback") not in CHANGE_ROLLBACKS:
                self.add("ERROR", rel, doc.key_line("rollback"), "E-CHANGE-FIELD",
                         f"rollback must be one of: {', '.join(CHANGE_ROLLBACKS)} "
                         f"(got {meta.get('rollback')!r})")
            targets = meta.get("targets")
            if not isinstance(targets, list) or not targets:
                self.add("ERROR", rel, doc.key_line("targets"), "E-CHANGE-FIELD",
                         "targets must be a non-empty list of entity pages")
            else:
                for target in targets:
                    if not self.page_exists(target):
                        self.add("ERROR", rel, doc.key_line("targets"), "E-CHANGE-FIELD",
                                 f"target {target} does not exist")
            for key in ("baseline", "after"):
                ref = meta.get(key)
                if ref is not None and not self.page_exists(ref):
                    self.add("ERROR", rel, doc.key_line(key), "E-CHANGE-FIELD", f"{key} {ref} does not exist")
                # A change recorded after the fact has no baseline; it says why instead.
                excused = key == "baseline" and isinstance(meta.get("baseline_unavailable"), str) \
                    and meta["baseline_unavailable"].strip()
                if ref is None and outcome in ("done", "rolled-back") and not excused:
                    self.add("ERROR", rel, 1, "E-CHANGE-FIELD", f"outcome {outcome} requires {key}"
                             + (" (or baseline_unavailable: <reason>)" if key == "baseline" else ""))
            repo = repo_root_for(self.wiki)
            for key in ("specs", "plans"):         # code behind the change, in the repository
                paths = meta.get(key)
                if paths is None:
                    continue
                if not isinstance(paths, list):
                    self.add("ERROR", rel, doc.key_line(key), "E-CHANGE-FIELD", f"{key} must be a list of repo paths")
                    continue
                for path in paths:
                    target = repo / str(path)
                    if not self.inside(target, repo) or not target.is_file():
                        self.add("ERROR", rel, doc.key_line(key), "E-CHANGE-FIELD", f"{key}: {path} does not exist")
            if date is None or (self.today - date).days <= limit:
                continue
            age = (self.today - date).days
            if outcome == "planned":
                self.add("WARN", rel, doc.key_line("outcome"), "W-PLANNED",
                         f"still planned {age} days after {meta['date']} (limit {limit}); "
                         "finish, abort or re-date it")
            for line, item in self._pending_items(doc):
                self.add("WARN", rel, line, "W-PENDING", f"open for {age} days: {item}")

    @staticmethod
    def _pending_items(doc: Doc) -> list[tuple[int, str]]:
        # Detect on prose (fences don't count), but report the original line so inline code
        # such as a snapshot name stays readable in the message.
        prose, _ = markdown.split_code(doc.text)
        original = doc.text.split("\n")
        items, inside = [], False
        for number, line in enumerate(prose.split("\n"), 1):
            if line.startswith("#"):
                inside = bool(PENDING_HEADING_RE.match(line))
                continue
            if inside and UNCHECKED_RE.match(line):
                items.append((number, UNCHECKED_RE.match(original[number - 1]).group(1).strip()))
        return items

    def check_contradictions(self, docs: dict[str, Doc]) -> None:
        for rel, doc in docs.items():
            prose, _ = markdown.split_code(doc.text)
            for number, line in enumerate(prose.split("\n"), 1):
                if CONTRADICTION_RE.match(line):
                    self.add("WARN", rel, number, "W-CONTRADICTION",
                             "unresolved contradiction: resolve it with the user or keep both versions, dated")

    def check_uncited(self, docs: dict[str, Doc]) -> None:
        for rel, doc in docs.items():
            if rel.split("/")[0] not in ("entities", "concepts"):
                continue
            for line, text in markdown.prose_paragraphs(doc.body, doc.body_line):
                if len(text.split()) >= UNCITED_MIN_WORDS and not CITATION_RE.search(text):
                    self.add("INFO", rel, line, "I-UNCITED",
                             "paragraph without a [[sources/...]] or [[changes/...]] citation")

    def check_frontmatter(self, docs: dict[str, Doc]) -> None:
        """Pages whose frontmatter the type-specific checks do not read still must parse."""
        for rel, doc in docs.items():
            if doc.meta_error and rel != "AGENTS.md" and rel.split("/")[0] not in ("sources", "entities", "changes"):
                self.add("ERROR", rel, 1, "E-FRONTMATTER", doc.meta_error)

    def check_schema(self, docs: dict[str, Doc]) -> None:
        """Keys the current template has and this wiki's schema lacks (their defaults apply)."""
        template = harness_root() / "templates" / "wiki" / "AGENTS.md"
        agents = self.wiki / "AGENTS.md"
        if not template.is_file() or not agents.is_file():
            return

        def keys(path: Path) -> list[str]:
            fm, _, _ = frontmatter.split(path.read_text(encoding="utf-8", errors="replace"))
            return [m.group(1) for line in (fm or "").split("\n") if (m := frontmatter.KEY_RE.match(line))]

        present = set(keys(agents))
        for key in keys(template):
            if key not in present:
                self.add("INFO", "AGENTS.md", 1, "I-SCHEMA",
                         f"`{key}` from the current template (templates/wiki/AGENTS.md) is missing; "
                         "its default applies, add it to change it")

    def scan_file(self, path: Path) -> None:
        path = Path(path).resolve()
        try:
            rel = path.relative_to(self.wiki).as_posix()
        except ValueError:
            rel = path.as_posix()
        data = path.read_bytes()
        try:
            text = decode(data).text
        except EncodingError as exc:
            self.add("ERROR", rel, 1, "E-ENCODING", f"{exc}; nothing in it can be checked for secrets")
            return
        if b"\x00" in data or not _is_utf8(data):
            self.add("ERROR", rel, 1, "E-ENCODING",
                     "not UTF-8 text (UTF-16, Latin-1...): git, grep and the agent cannot read it "
                     "reliably; re-capture it through bin/wiki-capture")
        if path.suffix == ".md":
            # key=value is too noisy for prose ("the token: rotate it"); scan it in code only.
            _, code = markdown.split_code(text)
            prose_rules = [rule for rule in self.secret_rules if rule.prose_safe]
            hits = redact.scan(text, prose_rules + [redact.PROSE_KEY_VALUE])
            hits += redact.scan(code, [rule for rule in self.secret_rules if not rule.prose_safe])
        else:
            hits = redact.scan(text, self.secret_rules)
        lines = text.split("\n")
        repo_rel = self.repo_path(path)
        for hit in hits:
            if self.allowed_hit(repo_rel, lines, hit):
                continue
            self.add("ERROR", rel, hit.line, "E-SECRET",
                     f"possible secret ({hit.rule}); remove it, or re-capture through bin/wiki-capture")
        flagged = {hit.line for hit in hits}
        for hit in redact.high_entropy(text):
            if hit.line not in flagged and not self.allowed_hit(repo_rel, lines, hit):
                self.add("WARN", rel, hit.line, "W-ENTROPY",
                         "long random-looking value next to a key that no rule redacted: "
                         "check it is not a secret")
        for hit in redact.scan(text, self.exposure_rules):
            hint = ("; write versions with a v prefix (v6.3.0.45) so they are not read as addresses"
                    if hit.rule == "ipv4" else "")
            what = "name" if hit.rule == "hostname" else "address"
            self.add("ERROR", rel, hit.line, "E-EXPOSURE", f"{hit.rule} {what} in an exposure: public wiki{hint}")

    def repo_path(self, path: Path) -> str | None:
        """`path` relative to the repository root (a staged copy under --paths-root maps to the
        file it stands for), or None outside both."""
        for root in (self.paths_root, self.repo):
            if root is not None and path.is_relative_to(root):
                return path.relative_to(root).as_posix()
        return None

    def allowed_hit(self, repo_rel: str | None, lines: list[str], hit: redact.Hit) -> bool:
        """True when an exception covers this hit; otherwise remember it for --print-allow."""
        if repo_rel is None:
            return False
        digest = short_hash(lines[hit.line - 1].encode("utf-8"))
        if any(entry.path == repo_rel and entry.digest == digest and entry.rule == hit.rule
               for entry in self.allow):
            self.allowed += 1
            return True
        self.candidates.append((repo_rel, digest, hit.rule))
        return False

    def check_allow(self) -> None:
        """An exception whose file is gone, or has no line with its hash, is left over."""
        for entry in self.allow:
            target = self.repo / entry.path
            digests = set()
            if target.is_file():
                digests = {short_hash(line.encode("utf-8"))
                           for line in decode(target.read_bytes()).text.split("\n")}
            if entry.digest not in digests:
                self.add("WARN", ALLOW_FILE, entry.line, "W-ALLOW-STALE",
                         f"no line of {entry.path} matches this exception any more; remove it")

    def check_secrets(self, docs: dict[str, Doc]) -> None:
        for path in self.secret_files():
            self.scan_file(path)
        self.check_allow()

    def run_secrets(self, paths=None) -> list[Finding]:
        targets = self.secret_files() if not paths else [
            Path(p) for p in paths if Path(p).is_file() and Path(p).name not in SCAN_SKIP]
        for path in targets:
            self.scan_file(path)
        return self.sorted_findings()


def report(findings: list[Finding], wiki: Path, allowed: int = 0) -> int:
    prefix = Path(wiki).as_posix().rstrip("/") + "/"
    for finding in findings:
        print(finding.format(prefix))
    counts = {level: sum(f.level == level for f in findings) for level in LEVEL_ORDER}
    tail = f", {allowed} allowed" if allowed else ""
    print(f"wiki-lint: {counts['ERROR']} error(s), {counts['WARN']} warning(s), {counts['INFO']} info{tail}")
    return 1 if counts["ERROR"] else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="wiki-lint", description="Deterministic checks for an llm-wiki.")
    parser.add_argument("--wiki", type=Path, help="wiki root (default: <harness>/wiki)")
    parser.add_argument("--only", choices=["secrets"],
                        help="run only the secret/exposure scan (used by the pre-commit hook)")
    parser.add_argument("--paths", nargs="+", type=Path, help="with --only secrets: scan just these files")
    parser.add_argument("--paths-root", type=Path,
                        help="with --paths: the directory the given files stand in for the repository "
                             "root (the pre-commit hook's staged copies)")
    parser.add_argument("--allow-file", type=Path,
                        help=f"reviewed exceptions of the secret scan (default: <wiki>/{ALLOW_FILE})")
    parser.add_argument("--print-allow", action="store_true",
                        help="with --only secrets: print an exception line, reason left empty, for "
                             "every secret finding, instead of the findings")
    parser.add_argument("--today", help="evaluate ages as of this date, YYYY-MM-DD (default: today)")
    parser.add_argument("--env-file", type=Path,
                        help="file whose secret values must never appear (default: <harness>/.env.local)")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.paths and args.only != "secrets":
        parser.error("--paths requires --only secrets")
    if args.print_allow and args.only != "secrets":
        parser.error("--print-allow requires --only secrets")
    if args.paths_root and not args.paths:
        parser.error("--paths-root requires --paths")
    missing = [str(path) for path in args.paths or [] if not Path(path).exists()]
    if missing:
        parser.error("--paths not found: " + ", ".join(missing))
    wiki = args.wiki or harness_root() / "wiki"
    if not Path(wiki).is_dir():
        print(f"wiki-lint: {wiki} is not a directory (run bin/init first?)", file=sys.stderr)
        return 2
    today = datetime.date.today()
    if args.today:
        today = parse_date(args.today)
        if today is None:
            parser.error("--today must be YYYY-MM-DD")
    linter = Linter(wiki, today, args.env_file or harness_root() / ".env.local",
                    args.allow_file, args.paths_root)
    findings = linter.run_secrets(args.paths) if args.only == "secrets" else linter.run()
    if args.print_allow:
        for path, digest, rule in dict.fromkeys(linter.candidates):
            print(f"{path} {digest} {rule}  # ")
        return 0
    return report(findings, wiki, linter.allowed)
