"""Small helpers shared by the wiki tools."""
from __future__ import annotations

import datetime
import hashlib
import re
from pathlib import Path

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def short_hash(data: bytes) -> str:
    """The wiki's source_hash: first 16 hex characters of sha256."""
    return hashlib.sha256(data).hexdigest()[:16]


def harness_root() -> Path:
    """Root of this harness checkout (lib/wikitools/util.py → two levels up)."""
    return Path(__file__).resolve().parents[2]


def repo_root_for(path: Path) -> Path:
    """Nearest ancestor of `path` (inclusive) holding .git; else path's parent."""
    path = Path(path).resolve()
    for candidate in (path, *path.parents):
        if (candidate / ".git").exists():
            return candidate
    return path.parent


def parse_date(value: object) -> datetime.date | None:
    """Strict YYYY-MM-DD string → date; anything else → None."""
    if not isinstance(value, str) or not DATE_RE.match(value):
        return None
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        return None
