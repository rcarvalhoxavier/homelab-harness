"""Decode captured bytes without hiding secrets behind the wrong codec.

A secret in UTF-16 (what Windows PowerShell 5.1 writes by default) is invisible to regexes
that read the bytes as UTF-8, and binary or compressed input cannot be scanned at all. So
capture decodes by BOM, detects BOM-less UTF-16, refuses binary, and says when it had to
fall back from UTF-8.
"""
from __future__ import annotations

import codecs
from dataclasses import dataclass

BOMS = (  # UTF-32 before UTF-16: FF FE 00 00 starts with FF FE
    (codecs.BOM_UTF32_LE, "utf-32-le"), (codecs.BOM_UTF32_BE, "utf-32-be"),
    (codecs.BOM_UTF8, "utf-8"), (codecs.BOM_UTF16_LE, "utf-16-le"), (codecs.BOM_UTF16_BE, "utf-16-be"),
)
CONTROL_OK = set("\t\n\r\f\v\x1b")   # ESC: colored terminal output


class EncodingError(ValueError):
    pass


@dataclass(frozen=True)
class Decoded:
    text: str
    encoding: str


def _guess_utf16(data: bytes) -> str | None:
    """ASCII text in UTF-16 has a NUL in every other byte."""
    sample = data[:4096]
    pairs = len(sample) // 2
    if pairs == 0:
        return None
    even = sum(1 for i in range(0, pairs * 2, 2) if sample[i] == 0)
    odd = sum(1 for i in range(1, pairs * 2, 2) if sample[i] == 0)
    if odd >= pairs * 0.3 and even <= pairs * 0.02:
        return "utf-16-le"
    if even >= pairs * 0.3 and odd <= pairs * 0.02:
        return "utf-16-be"
    return None


def _check_text(text: str, encoding: str) -> Decoded:
    controls = sum(1 for ch in text if ord(ch) < 32 and ch not in CONTROL_OK)
    if controls > max(8, len(text) // 10):
        raise EncodingError("input looks binary (control bytes): secrets inside it cannot be scanned; "
                            "capture text output, or pass --encoding if it really is text")
    return Decoded(text, encoding)


def decode(data: bytes, forced: str | None = None) -> Decoded:
    if forced:
        return Decoded(data.decode(forced, errors="replace").lstrip("﻿"), forced)
    for bom, codec in BOMS:
        if data.startswith(bom):
            return _check_text(data[len(bom):].decode(codec, errors="replace"), codec)
    if b"\x00" in data:
        guess = _guess_utf16(data)
        if guess is None:
            raise EncodingError("input contains NUL bytes: binary or an unknown encoding; "
                                "convert it first (iconv -f <codec> -t utf-8) or pass --encoding")
        return _check_text(data.decode(guess, errors="replace"), guess)
    try:
        return _check_text(data.decode("utf-8"), "utf-8")
    except UnicodeDecodeError:
        return _check_text(data.decode("cp1252", errors="replace"), "cp1252")
