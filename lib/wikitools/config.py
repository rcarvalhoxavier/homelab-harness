"""Wiki schema config (the frontmatter of <wiki>/AGENTS.md) and fixed vocabularies."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import frontmatter
from .util import SLUG_RE

BASE_TRUST_LEVELS = ("measured", "internal-reviewed", "vendor", "third-party",
                     "user", "agent-report", "web")
ENTITY_KINDS = ("host", "guest", "service", "device", "storage", "network", "external", "system")
ENTITY_STATUSES = ("active", "retired", "evaluating")
CHANGE_OUTCOMES = ("planned", "done", "rolled-back", "aborted")
CHANGE_ROLLBACKS = ("snapshot", "backup", "none", "other")
SOURCE_TYPES = ("measurement", "document", "report", "article", "changelog", "conversation")
SOURCE_REQUIRED = ("title", "date", "type", "source", "source_hash", "trust_level")
PAGE_DIRS = ("entities", "concepts", "sources", "changes", "analyses")
WIKI_DIRS = ("raw",) + PAGE_DIRS
LOG_OPS = ("ingest", "query", "lint", "update", "capture", "change", "diagnose", "reconcile")


class ConfigError(ValueError):
    def __init__(self, message: str, line: int = 1):
        super().__init__(message)
        self.line = line


@dataclass(frozen=True)
class WikiConfig:
    mode: str = "personal"
    exposure: str = "private"
    language: str = "en"
    stale_after_days: int = 90
    pending_after_days: int = 14
    extra_trust_levels: tuple[str, ...] = ()
    extra_entity_kinds: tuple[str, ...] = ()

    @property
    def trust_levels(self) -> tuple[str, ...]:
        return BASE_TRUST_LEVELS + self.extra_trust_levels

    @property
    def entity_kinds(self) -> tuple[str, ...]:
        return ENTITY_KINDS + self.extra_entity_kinds


def _choice(data: dict, key: str, choices: tuple[str, ...]) -> str:
    value = data.get(key)
    if value not in choices:
        raise ConfigError(f"{key} must be one of: {', '.join(choices)} (got {value!r})")
    return value


def _positive_int(data: dict, key: str, default: int) -> int:
    value = data.get(key, default)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ConfigError(f"{key} must be a positive integer (got {value!r})")
    return value


def _name_list(data: dict, key: str, builtins: tuple[str, ...]) -> tuple[str, ...]:
    value = data.get(key) or []
    if not isinstance(value, list) or not all(isinstance(x, str) and SLUG_RE.match(x) for x in value):
        raise ConfigError(f"{key} must be a list of kebab-case names (got {value!r})")
    clash = sorted(set(value) & set(builtins))
    if clash:
        raise ConfigError(f"{key} repeats built-in names: {', '.join(clash)}")
    return tuple(value)


def load_config(wiki_dir: Path) -> WikiConfig:
    path = Path(wiki_dir) / "AGENTS.md"
    if not path.is_file():
        raise ConfigError(f"{path} not found — create the wiki with bin/init")
    fm, _, _ = frontmatter.split(path.read_text(encoding="utf-8"))
    if fm is None:
        raise ConfigError(f"{path} has no frontmatter block")
    try:
        data = frontmatter.parse(fm)
    except frontmatter.FrontmatterError as exc:
        raise ConfigError(str(exc), exc.line) from exc
    if data.get("harness_schema") != 1:
        raise ConfigError(f"harness_schema must be 1 (got {data.get('harness_schema')!r})")
    language = data.get("language", "en")
    if not isinstance(language, str) or not language.strip():
        raise ConfigError(f"language must be a non-empty string (got {language!r})")
    return WikiConfig(
        mode=_choice(data, "mode", ("personal", "team")),
        exposure=_choice(data, "exposure", ("private", "public")),
        language=language,
        stale_after_days=_positive_int(data, "stale_after_days", 90),
        pending_after_days=_positive_int(data, "pending_after_days", 14),
        extra_trust_levels=_name_list(data, "extra_trust_levels", BASE_TRUST_LEVELS),
        extra_entity_kinds=_name_list(data, "extra_entity_kinds", ENTITY_KINDS),
    )
