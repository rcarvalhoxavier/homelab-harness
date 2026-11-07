"""Markdown helpers: tell prose from code, find wikilinks and prose paragraphs."""
from __future__ import annotations

import re

# Any indentation: fences nested under list items are still fences.
FENCE_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})")
INLINE_CODE_RE = re.compile(r"(`+)(.+?)\1")
# A target never starts with whitespace or "-": that is a shell test, `[[ -d x ]]` or `[[-d x]]`.
WIKILINK_RE = re.compile(r"\[\[(?![\s-])([^\[\]|#\n]+?)(?:#[^\[\]|\n]*)?(?:\|[^\[\]\n]*)?\]\]")
BLOCK_START_RE = re.compile(r"^\s*(?:#|[-*+]\s|\d+[.)]\s|\||>)")


def _blank(text: str) -> str:
    return re.sub(r"[^\n]", " ", text)


def split_code(text: str) -> tuple[str, str]:
    """Return (prose, code), both shaped exactly like `text`.

    prose has fenced blocks and inline code blanked; code has everything else
    blanked. Line numbers and columns stay valid in both.
    """
    prose_lines, code_lines = [], []
    fence = None
    for line in text.split("\n"):
        match = FENCE_RE.match(line)
        if fence is not None:
            prose_lines.append(_blank(line))
            code_lines.append(line)
            if (match and match.group(1)[0] == fence[0] and len(match.group(1)) >= len(fence)
                    and not line.strip()[len(match.group(1)):].strip()):
                fence = None
            continue
        if match:
            fence = match.group(1)
            prose_lines.append(_blank(line))
            code_lines.append(line)
            continue
        prose_parts, code_parts, last = [], [], 0
        for inline in INLINE_CODE_RE.finditer(line):
            prose_parts += [line[last:inline.start()], _blank(inline.group(0))]
            code_parts += [_blank(line[last:inline.start()]), inline.group(0)]
            last = inline.end()
        prose_parts.append(line[last:])
        code_parts.append(_blank(line[last:]))
        prose_lines.append("".join(prose_parts))
        code_lines.append("".join(code_parts))
    return "\n".join(prose_lines), "\n".join(code_lines)


def wikilinks(text: str) -> list[tuple[int, str]]:
    """(line, target) for every [[target]], [[target|alias]] or [[target#h]] in prose."""
    prose, _ = split_code(text)
    found = []
    for number, line in enumerate(prose.split("\n"), 1):
        for match in WIKILINK_RE.finditer(line):
            found.append((number, match.group(1).strip()))
    return found


def prose_paragraphs(text: str, first_line: int = 1) -> list[tuple[int, str]]:
    """Blank-line separated prose blocks (not headings, lists, tables, quotes or code)."""
    prose, _ = split_code(text)
    paragraphs, block, start = [], [], first_line
    for number, line in enumerate(prose.split("\n") + [""], first_line):
        if line.strip():
            if not block:
                start = number
            block.append(line)
            continue
        if block and not BLOCK_START_RE.match(block[0]):
            paragraphs.append((start, " ".join(part.strip() for part in block)))
        block = []
    return paragraphs
