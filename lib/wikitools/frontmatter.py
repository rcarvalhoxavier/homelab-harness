"""Minimal YAML-frontmatter subset: flat `key: value` lines.

Values: quoted strings, integers, true/false, inline lists [a, b], block lists
(`key:` followed by `  - item` lines, as Obsidian writes them) and inline maps
{k: v}. No nesting beyond one level: the wiki's frontmatter never needs more,
and the stdlib has no YAML parser.
"""
from __future__ import annotations

import json
import re

KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*:(.*)$")
ITEM_RE = re.compile(r"^[ \t]*-[ \t]+(.*)$")
INT_RE = re.compile(r"^-?\d+$")
NEEDS_QUOTES_RE = re.compile(r"""[:#\[\]{},"']|^\s|\s$|^-?\d+$|^(?:true|false)$""")


class FrontmatterError(ValueError):
    def __init__(self, line: int, message: str):
        super().__init__(f"line {line}: {message}")
        self.line = line


def split(text: str) -> tuple[str | None, str, int]:
    """Return (frontmatter, body, first body line). No frontmatter → (None, text, 1)."""
    text = text.removeprefix("\ufeff")    # editors on Windows add a BOM
    lines = text.split("\n")
    if not lines or lines[0].rstrip() != "---":
        return None, text, 1
    for i in range(1, len(lines)):
        if lines[i].rstrip() == "---":
            return "\n".join(lines[1:i]), "\n".join(lines[i + 1:]), i + 2
    return None, text, 1


def _strip_comment(raw: str) -> str:
    quote = None
    for i, ch in enumerate(raw):
        if quote:
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch == "#" and (i == 0 or raw[i - 1] in " \t"):
            return raw[:i]
    return raw


def _split_top(inner: str) -> list[str]:
    """Split on commas that are not inside quotes or brackets."""
    parts, current, depth, quote = [], [], 0, None
    for ch in inner:
        if quote:
            current.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append("".join(current))
            current = []
            continue
        current.append(ch)
    if "".join(current).strip():
        parts.append("".join(current))
    return [part.strip() for part in parts]


def parse_value(raw: str, line: int = 0):
    value = raw.strip()
    if value == "":
        return None
    if value[0] in "\"'":
        if len(value) < 2 or value[-1] != value[0]:
            raise FrontmatterError(line, f"unterminated string: {value}")
        if value[0] == "'":
            return value[1:-1].replace("''", "'")      # YAML single quotes: '' is one quote
        try:
            return json.loads(value)                    # dumps() escapes like JSON
        except ValueError:
            return value[1:-1]
    if value.startswith("["):
        if not value.endswith("]"):
            raise FrontmatterError(line, f"unterminated list: {value}")
        return [parse_value(part, line) for part in _split_top(value[1:-1])]
    if value.startswith("{"):
        if not value.endswith("}"):
            raise FrontmatterError(line, f"unterminated map: {value}")
        result = {}
        for part in _split_top(value[1:-1]):
            match = KEY_RE.match(part)
            if not match:
                raise FrontmatterError(line, f"bad map entry: {part}")
            result[match.group(1)] = parse_value(match.group(2), line)
        return result
    if INT_RE.match(value):
        return int(value)
    if value in ("true", "false"):
        return value == "true"
    return value


def parse(fm: str, first_line: int = 2) -> dict:
    """Parse frontmatter text. first_line is the file line of fm's first line."""
    data: dict = {}
    lines = fm.split("\n")
    index = 0
    while index < len(lines):
        raw, line = lines[index], first_line + index
        index += 1
        text = _strip_comment(raw).rstrip()
        if not text.strip():
            continue
        match = KEY_RE.match(text)
        if not match:
            raise FrontmatterError(line, f"expected 'key: value' (lists go inline as [a, b], or as "
                                         f"'  - item' lines under their key), got: {raw.strip()}")
        key = match.group(1)
        if key in data:
            raise FrontmatterError(line, f"duplicate key: {key}")
        value = parse_value(match.group(2), line)
        if value is None:                              # block list: `key:` then `  - item` lines
            items = []
            while index < len(lines) and ITEM_RE.match(_strip_comment(lines[index]).rstrip()):
                item = ITEM_RE.match(_strip_comment(lines[index]).rstrip()).group(1)
                items.append(parse_value(item, first_line + index))
                index += 1
            value = items or None
        data[key] = value
    return data


def _dump_scalar(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    text = str(value)
    if text == "" or NEEDS_QUOTES_RE.search(text):
        return json.dumps(text, ensure_ascii=False)
    return text


def dumps(data: dict) -> str:
    lines = ["---"]
    for key, value in data.items():
        if isinstance(value, list):
            rendered = "[" + ", ".join(_dump_scalar(v) for v in value) + "]"
        elif isinstance(value, dict):
            rendered = "{" + ", ".join(f"{k}: {_dump_scalar(v)}" for k, v in value.items()) + "}"
        else:
            rendered = _dump_scalar(value)
        lines.append(f"{key}: {rendered}")
    lines.append("---")
    return "\n".join(lines) + "\n"
