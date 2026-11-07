"""Secret and network-identifier redaction shared by wiki-capture and wiki-lint.

Best effort by design: regexes catch the common shapes, `.env.local` values catch the
user's actual secrets, and <wiki>/.capture-patterns catches the rest. The llm-wiki skill
still requires reading every capture before it is committed, and wiki-lint adds detectors
of its own (encoding and entropy checks) on top of these rules.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

SECRET_WORD = (r"(?:pass(?:word|wd|phrase)?|pwhash|pwd|pw|secret|token|api[_-]?key|private[_-]?key"
               r"|access[_-]?key|auth[_-]?key|psk|pre-?shared[_-]?key|community|credentials?"
               r"|cookie|pin)")
SECRET_NAME_RE = re.compile(SECRET_WORD, re.IGNORECASE)
SUFFIX_OK = ("salt", "hash", "file", "s")

# Values that are clearly not secrets: markers and placeholders, $VAR references,
# booleans, masks and empty strings. Short numbers are decided per key (NUMERIC_KEY_RE).
PLACEHOLDER_RE = re.compile(
    r"^(?:<[^>]*>.*|\$\{?\w+\}?|null|none|nil|true|false|yes|no|on|off|\*+|x+|-|)$", re.IGNORECASE)
NUMERIC_KEY_RE = re.compile(
    r"(?i)(?:ttl|length|len|timeout|size|expir\w*|count|max|min|lifetime|age|port|retries|days"
    r"|hours|minutes|seconds|interval|limit|version|index|id)$")
NSSWITCH_RE = re.compile(r"^(?:files|compat|systemd|sss|ldap|nis|db|winbind)\b")
KNOWN_WORDS = {"required", "optional", "changed", "rotated", "unset", "empty", "stored", "redacted",
               "hidden", "default", "disabled", "enabled", "unknown", "expired", "missing", "same",
               "see", "set", "configured", "generated", "random", "encrypted", "hashed", "example",
               "placeholder", "elsewhere", "vault"}
SECRET_SYMBOL_RE = re.compile(r"[\d!@#$%^&*+=?~]")
VALUE_GROUPS = ("dq", "sq", "bare")


@dataclass(frozen=True)
class Rule:
    name: str                        # label used in lint findings
    bucket: str                      # counts bucket: secret | ip | mac | host
    regex: re.Pattern
    group: int | str | tuple = 0     # group(s) holding the sensitive value; first that matched
    marker: str | None = None        # fixed replacement; None → numbered placeholder
    prefix: str | None = None        # placeholder prefix, e.g. "IP" → <IP-1>
    skip: Callable[[re.Match], bool] | None = None
    prose_safe: bool = True          # False → too noisy for Markdown prose (lint scans code only)


@dataclass(frozen=True)
class Hit:
    line: int
    rule: str
    bucket: str


@dataclass
class Redaction:
    text: str
    counts: dict


def _span(match: re.Match, group) -> tuple[tuple[int, int], str]:
    if isinstance(group, tuple):
        for name in group:
            if name in match.re.groupindex and match.group(name) is not None:
                return match.span(name), match.group(name)
        return match.span(0), match.group(0)
    return match.span(group), match.group(group)


def secret_key(key: str) -> bool:
    """True when `key` names a secret: the secret word ends the key or one of its segments
    (db_password, dbPassword, PresharedKey, passwordSalt), not when it starts a longer word
    (passthrough, tokenizer, spinner)."""
    bare = key.strip("\"'`")
    for match in SECRET_NAME_RE.finditer(bare):
        after = bare[match.end():]
        if not after or after[0] in "_.-" or after[0].isdigit():
            return True
        if after[0].isupper() and bare[match.end() - 1].islower():
            return True
        for suffix in SUFFIX_OK:
            rest = after[len(suffix):]
            if after.lower().startswith(suffix) and (not rest or rest[0] in "_.-" or rest[0].isdigit()
                                                      or rest[0].isupper()):
                return True
    return False


def not_secret_value(key: str, value: str) -> bool:
    text = value.strip()
    if PLACEHOLDER_RE.match(text):
        return True
    name = key.strip("\"'`")
    if text.isdigit() and len(text) <= 6:      # a PIN when the key says so; else a number
        return not name or bool(NUMERIC_KEY_RE.search(name))
    return name.lower() == "passwd" and bool(NSSWITCH_RE.match(text))


def looks_secret(value: str, key: str = "") -> bool:
    """Prose heuristic: one token that is long, or has a digit or a symbol."""
    token = value.strip("\"'`").rstrip(".,;:!?)")
    if not token or " " in token or "://" in token:
        return False
    if PLACEHOLDER_RE.match(token) or token.lower() in KNOWN_WORDS:
        return False
    if len(token) >= 12:
        return True
    return len(token) >= 8 and bool(SECRET_SYMBOL_RE.search(token))


def _pass_status(match: re.Match) -> bool:
    """`PASS:` (uppercase, then a colon) is a test or check result, not a password."""
    if "key" not in match.re.groupindex or match.group("key") != "PASS":
        return False
    return match.string[match.end("key"):match.end()].lstrip(" \t").startswith(":")


def _kv_skip(match: re.Match) -> bool:
    key = match.group("key") if "key" in match.re.groupindex else ""
    if key and not secret_key(key) or _pass_status(match):
        return True
    return not_secret_value(key, _span(match, VALUE_GROUPS)[1])


def _value_skip(match: re.Match) -> bool:
    return not_secret_value("", _span(match, VALUE_GROUPS)[1])


def _url_password_skip(match: re.Match) -> bool:
    value = match.group("value")
    return value.startswith("<REDACTED") or bool(re.match(r"^\d+(?:/|$)", value))


def _ipv4_skip(match: re.Match) -> bool:
    ip = match.group(0)
    if ip.startswith(("127.", "255.")) or ip == "0.0.0.0":
        return True
    text = match.string
    line_start = text.rfind("\n", 0, match.start()) + 1
    before = text[line_start:match.start()]
    if re.search(r"(?:[\w.-]+/)+[\w.-]+:$", before):      # image tag: repo/name:6.3.0.45
        return True
    if re.match(r"-\d", text[match.end():match.end() + 2]):  # Debian revision: 5.15.20.20-1
        return True
    # A four-part number right after "version", "firmware", "build", "v"... or in a
    # dpkg listing (`ii  name  5.15.20.20`) is a version, not an address.
    return bool(re.search(r"(?i)(?:\bv|version\W*|\bver\W*|firmware\W*|\bfw\W*|\bbuild\W*"
                          r"|\brelease\W*|^ii\s+\S+\s+)$", before))


_OCTET = r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)"
_H = r"[0-9A-Fa-f]{1,4}"
_KEY = r"[\"'`]?[A-Za-z0-9_.-]*" + SECRET_WORD + r"[A-Za-z0-9_.-]*[\"'`]?"
_SEP = r"[ \t]*(?:=>|[=:])[ \t]*"      # `=>` first: PHP/Perl/Ruby hashes
_QUOTED = r"\"(?P<dq>[^\"\r\n]*)\"|'(?P<sq>[^'\r\n]*)'"

PRIVATE_KEY = Rule(
    "private-key", "secret",
    # PEM and PGP private keys and OpenVPN static keys; a block cut off before its END line
    # runs to the end. PUBLIC KEY and CERTIFICATE blocks are not secrets and stay.
    re.compile(r"-----BEGIN (?:[A-Z0-9 ]*PRIVATE KEY(?: BLOCK)?|OpenVPN Static key V\d)-----.*?"
               r"(?:-----END [^\r\n]*?-----|\Z)", re.S),
    marker="<REDACTED:private-key>")
PUTTY_KEY = Rule(
    "private-key", "secret",
    re.compile(r"^Private-Lines:[ \t]*\d+\r?\n(?P<value>[A-Za-z0-9+/=]+(?=\r?$)(?:\r?\n[A-Za-z0-9+/=]+(?=\r?$))*)",
               re.M),
    group="value", marker="<REDACTED:private-key>")
BASE64_PEM = Rule(
    "private-key", "secret",     # base64 of "-----BEGIN", as in pfSense/OPNsense <prv> elements
    re.compile(r"\bLS0tLS1CRUdJTi[A-Za-z0-9+/=]*"),
    marker="<REDACTED:private-key>")
KNOWN_TOKEN = Rule(
    "known-token", "secret",
    re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|glpat-[A-Za-z0-9_-]{20,}"
               r"|xox[abprs]-[A-Za-z0-9-]{10,}|tskey-[A-Za-z0-9-]{10,}|sk-(?:proj-|ant-)?[A-Za-z0-9_-]{20,}"
               r"|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{35}|hf_[A-Za-z0-9]{30,})"),
    marker="<REDACTED:token>")
URL_CREDENTIALS = Rule(
    "url-credentials", "secret",
    # The password runs to the last "@" before the host, so "@" and "/" inside it are covered.
    re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s:/@<>]+:(?P<value>\S+?)@(?=[^\s@/:]+(?:[:/?#\s'\")]|$))",
               re.IGNORECASE | re.MULTILINE),
    group="value", marker="<REDACTED:password>", skip=_url_password_skip)
URL_TOKEN_USER = Rule(
    "url-credentials", "secret",
    re.compile(r"://(?P<value>[A-Za-z0-9_-]{20,})@"),
    group="value", marker="<REDACTED:token>",
    skip=lambda m: not (re.search(r"\d", m.group("value")) and re.search(r"[A-Za-z]", m.group("value"))))
TELEGRAM = Rule(
    "known-token", "secret",
    re.compile(r"\bbot(?P<value>\d{6,}:[A-Za-z0-9_-]{30,})"),
    group="value", marker="<REDACTED:token>")
QUERY_SECRET = Rule(
    "query-parameter", "secret",
    re.compile(r"[?&](?:key|apikey|api_key|access_token|token|auth|sig|signature|password|secret)"
               r"=(?P<bare>[^&\s#]+)", re.IGNORECASE),
    group="bare", marker="<REDACTED:secret>", skip=_value_skip)
BEARER = Rule(
    "bearer-token", "secret",
    re.compile(r"(?i)\bbearer\s+(?P<value>[A-Za-z0-9\-._~+/]{8,}=*)"),
    group="value", marker="<REDACTED:token>", skip=lambda m: m.group("value").isalpha())
BASIC_AUTH = Rule(
    "basic-auth", "secret",
    re.compile(r"(?i)\bauthorization:[ \t]*basic[ \t]+(?P<value>[A-Za-z0-9+/]{8,}={0,2})"),
    group="value", marker="<REDACTED:token>")
JWT = Rule(
    "jwt", "secret",
    re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}"),
    marker="<REDACTED:token>")
SHADOW_HASH = Rule(
    "password-hash", "secret",
    re.compile(r"^[a-z_][a-z0-9_.-]*\$?:(?P<value>\$[0-9a-z]+\$[^:\n]+):", re.MULTILINE),
    group="value", marker="<REDACTED:password-hash>")
HTPASSWD = Rule(
    "password-hash", "secret",
    re.compile(r"^[^:\s#]+:(?P<value>\$(?:apr1|2[aby]|[156y]|sha1)\$[^\s:]+|\{SHA\}[A-Za-z0-9+/=]+)(?=\s|$)",
               re.MULTILINE),
    group="value", marker="<REDACTED:password-hash>")
XML_SECRET = Rule(
    "xml-element", "secret",
    re.compile(r"<(?P<key>[\w:.-]*" + SECRET_WORD + r"[\w:.-]*)>(?P<bare>[^<\n]+)</(?P=key)>",
               re.IGNORECASE),
    group="bare", marker="<REDACTED:secret>", skip=_kv_skip)
UCI_OPTION = Rule(
    "uci-option", "secret",
    re.compile(r"^[ \t]*option[ \t]+(?P<key>key|[\w]*(?:pass|secret|token|psk|password)[\w]*)[ \t]+"
               r"(?:" + _QUOTED + r"|(?P<bare>[^\s'\"]+))", re.MULTILINE),
    group=VALUE_GROUPS, marker="<REDACTED:secret>", skip=_value_skip, prose_safe=False)
UCI_SHOW = Rule(
    "uci-option", "secret",
    re.compile(r"\b[\w-]+(?:\.[\w@\[\]-]+)*\.key=(?:" + _QUOTED + r"|(?P<bare>[^\s'\"]+))"),
    group=VALUE_GROUPS, marker="<REDACTED:secret>", skip=_value_skip, prose_safe=False)
SNMP_COMMUNITY = Rule(
    "snmp-community", "secret",
    re.compile(r"(?<![\w-])(?:[rR][oOwW]community6?|snmp-server[ \t]+community)[ \t]+(?P<bare>\S+)"),
    group="bare", marker="<REDACTED:secret>", skip=_value_skip, prose_safe=False)
CISCO_SECRET = Rule(
    "cisco-secret", "secret",
    re.compile(r"(?<![\w-])(?:username[ \t]+\S+[ \t]+(?:password|secret)[ \t]+(?:[0-9][ \t]+)?"
               r"|(?:password|secret)[ \t]+[0-9][ \t]+)(?P<bare>\S+)"),
    group="bare", marker="<REDACTED:secret>", skip=_value_skip, prose_safe=False)
CLI_PASSWORD = Rule(
    "cli-password", "secret",
    re.compile(r"(?i)(?:\bsshpass[ \t]+-p[ \t]*|(?<![\w-])--pass(?:word|wd)?[ \t]+)"
               r"(?:" + _QUOTED + r"|(?P<bare>[^\s\"']+))"),
    group=VALUE_GROUPS, marker="<REDACTED:password>", skip=_value_skip, prose_safe=False)
CLI_USER = Rule(
    "cli-user", "secret",
    re.compile(r"(?<!\S)(?:-u|--user)[ \t]+[^\s:]+:(?P<bare>\S+)"),
    group="bare", marker="<REDACTED:password>", skip=_value_skip, prose_safe=False)
MYSQL_PASSWORD = Rule(
    "cli-password", "secret",
    re.compile(r"\bmysql(?:dump|admin|import|check|show)?\b[^\r\n]*?[ \t]-p(?P<bare>[^\s-]\S*)"),
    group="bare", marker="<REDACTED:password>", skip=_value_skip, prose_safe=False)
REGISTRY_LOGIN = Rule(
    "cli-password", "secret",
    re.compile(r"\b(?:docker|podman|nerdctl|buildah|skopeo|helm)[ \t]+(?:registry[ \t]+)?login\b"
               r"[^\r\n]*?[ \t](?:-p|--password)[ \t]+(?P<bare>\S+)"),
    group="bare", marker="<REDACTED:password>", skip=_value_skip, prose_safe=False)
YAML_BLOCK = Rule(
    "key-value", "secret",
    re.compile(r"^(?P<indent>[ \t]*)(?P<key>[\w.-]*" + SECRET_WORD + r"[\w.-]*)[ \t]*:[ \t]*[|>][-+]?[ \t]*\r?\n"
               r"(?P<bare>(?P=indent)[ \t]+[^\r\n]*(?:\r?\n(?P=indent)[ \t]+[^\r\n]*)*)",
               re.IGNORECASE | re.MULTILINE),
    group="bare", marker="<REDACTED:secret>", skip=_kv_skip, prose_safe=False)
YAML_NEXT_LINE = Rule(
    "key-value", "secret",
    re.compile(r"^(?P<indent>[ \t]*)(?P<key>[\w.-]*" + SECRET_WORD + r"[\w.-]*)[ \t]*:[ \t]*\r?\n"
               r"(?P=indent)[ \t]+(?P<bare>[^\s#-][^\r\n]*?)(?=[ \t]*\r?$)",
               re.IGNORECASE | re.MULTILINE),
    group="bare", marker="<REDACTED:secret>", skip=_kv_skip, prose_safe=False)
# A secret-named key that starts its line owns the rest of the line (minus a trailing
# comma/semicolon and a ` # comment`): unquoted values may contain spaces, & or commas.
KEY_VALUE_LINE = Rule(
    "key-value", "secret",
    re.compile(
        r"^[ \t]*(?:export[ \t]+|-[ \t]+|-{1,2})?(?P<key>" + _KEY + r")" + _SEP
        + r"(?:" + _QUOTED + r"|(?P<bare>[^\s\"'>|][^\r\n]*?))"
        + r"(?=[ \t]*[,;]?(?:[ \t]+#[^\r\n]*)?[ \t]*\r?$)",
        re.IGNORECASE | re.MULTILINE),
    group=VALUE_GROUPS, marker="<REDACTED:secret>", skip=_kv_skip, prose_safe=False)
KEY_VALUE = Rule(
    "key-value", "secret",
    re.compile(
        r"(?<![A-Za-z0-9_.-])(?P<key>" + _KEY + r")" + _SEP
        + r"(?:" + _QUOTED + r"|(?P<bare>[^\s,;&}\]>|'\"][^\s,;&}\]]*))",
        re.IGNORECASE),
    group=VALUE_GROUPS, marker="<REDACTED:secret>", skip=_kv_skip, prose_safe=False)
# Markdown/ASCII table row whose first cell names a secret: | password | CorrectHorse99 |
TABLE_KEY_VALUE = Rule(
    "table-cell", "secret",
    re.compile(r"^\|[^|\n]*" + SECRET_WORD + r"[^|\n]*\|[ \t]*(?P<value>[^|\n]*?)[ \t]*\|",
               re.IGNORECASE | re.MULTILINE),
    group="value", marker="<REDACTED:secret>", skip=lambda m: not looks_secret(m.group("value")))
# For Markdown prose, where "the token: rotate it yearly" is common: only values that look
# like secrets. Used by wiki-lint; captures use the stricter KEY_VALUE rules.
PROSE_KEY_VALUE = Rule(
    "key-value", "secret", KEY_VALUE.regex, group=VALUE_GROUPS, marker="<REDACTED:secret>",
    skip=lambda m: (not secret_key(m.group("key")) or _pass_status(m)
                    or not looks_secret(_span(m, VALUE_GROUPS)[1])))

MAC = Rule(
    "mac", "mac",
    re.compile(r"(?<![\w:-])[0-9A-Fa-f]{2}([:-])(?:[0-9A-Fa-f]{2}\1){4}[0-9A-Fa-f]{2}(?![\w:-])"),
    prefix="MAC")
MAC_DOTTED = Rule(
    "mac", "mac", re.compile(r"(?<![\w.])[0-9A-Fa-f]{4}\.[0-9A-Fa-f]{4}\.[0-9A-Fa-f]{4}(?![\w.])"),
    prefix="MAC")
MAC_BARE = Rule(
    "mac", "mac",     # a bare 12-digit MAC only where the line says it is one
    re.compile(r"(?i)(?:mac|hwaddr|ether|bssid|lladdr)\b[^\r\n]*?(?<![\w:.-])(?P<value>[0-9a-f]{12})(?![\w:.-])"),
    group="value", prefix="MAC")
IPV4 = Rule(
    "ipv4", "ip",
    re.compile(rf"(?<![\w.])(?:{_OCTET}\.){{3}}{_OCTET}(?!\.?\d)"),
    prefix="IP", skip=_ipv4_skip)
IPV6 = Rule(
    "ipv6", "ip",
    re.compile(rf"(?<![\w:])(?:(?:{_H}:){{7}}{_H}|(?:{_H}(?::{_H})*)?::(?:{_H}(?::{_H})*)?)(?![\w:])"),
    prefix="IPV6", skip=lambda m: m.group(0) in ("::", "::1"))
HOSTNAME = Rule(
    "hostname", "host",   # home-network and dynamic-DNS names identify a home
    re.compile(r"(?i)\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+(?:lan|local|home|internal|localdomain"
               r"|home\.arpa|duckdns\.org|ddns\.net|no-ip\.(?:com|org|biz)|dynu\.(?:com|net)"
               r"|afraid\.org|myfritz\.net|synology\.me|tplinkdns\.com|ts\.net)\b"),
    prefix="HOST")

SECRET_RULES = (PRIVATE_KEY, PUTTY_KEY, BASE64_PEM, KNOWN_TOKEN, URL_CREDENTIALS, URL_TOKEN_USER,
                TELEGRAM, QUERY_SECRET, BEARER, BASIC_AUTH, JWT, SHADOW_HASH, HTPASSWD, XML_SECRET,
                UCI_OPTION, UCI_SHOW, SNMP_COMMUNITY, CISCO_SECRET, CLI_PASSWORD, CLI_USER,
                MYSQL_PASSWORD, REGISTRY_LOGIN, YAML_BLOCK, YAML_NEXT_LINE, KEY_VALUE_LINE,
                KEY_VALUE, TABLE_KEY_VALUE)
EXPOSURE_RULES = (MAC, MAC_DOTTED, MAC_BARE, IPV4, IPV6, HOSTNAME)
BUCKETS = ("secret", "ip", "mac", "host")


def build_rules(literals=(), custom=(), exposure: str = "private") -> list[Rule]:
    rules: list[Rule] = []
    usable = sorted({value for value in literals if len(value) >= 6}, key=len, reverse=True)
    if usable:
        rules.append(Rule("env-literal", "secret",
                          re.compile("|".join(re.escape(value) for value in usable)),
                          marker="<REDACTED:secret>"))
    rules.extend(SECRET_RULES)
    rules.extend(Rule("custom", "secret", pattern, marker="<REDACTED:custom>") for pattern in custom)
    if exposure == "public":
        rules.extend(EXPOSURE_RULES)
    return rules


def redact(text: str, literals=(), custom=(), exposure: str = "private", keep=()) -> Redaction:
    """Redact `text`. `keep` regexes protect their matches from the exposure rules."""
    counts = {bucket: 0 for bucket in BUCKETS}
    numbering: dict[str, dict[str, str]] = {}
    for rule in build_rules(literals, custom, exposure):
        kept = []
        if rule.prefix and keep:
            kept = [m.span() for pattern in keep for m in pattern.finditer(text)]

        def replace(match: re.Match, rule: Rule = rule, kept=kept) -> str:
            if rule.skip is not None and rule.skip(match):
                return match.group(0)
            (start, end), value = _span(match, rule.group)
            if any(k_start <= start and end <= k_end for k_start, k_end in kept):
                return match.group(0)
            if rule.marker is not None:
                replacement = rule.marker
            else:
                table = numbering.setdefault(rule.prefix, {})
                replacement = table.setdefault(value.lower(), f"<{rule.prefix}-{len(table) + 1}>")
            counts[rule.bucket] += 1
            whole, offset = match.group(0), match.start()
            return whole[:start - offset] + replacement + whole[end - offset:]
        text = rule.regex.sub(replace, text)
    return Redaction(text, counts)


def scan(text: str, rules) -> list[Hit]:
    """Where `rules` would redact something in `text`, without changing it."""
    hits = set()
    for rule in rules:
        for match in rule.regex.finditer(text):
            if rule.skip is not None and rule.skip(match):
                continue
            (start, _), _ = _span(match, rule.group)
            hits.add(Hit(text.count("\n", 0, start) + 1, rule.name, rule.bucket))
    return sorted(hits, key=lambda hit: (hit.line, hit.rule))


ENTROPY_RE = re.compile(r"(?P<key>[A-Za-z0-9_.-]+)[ \t]*[=:][ \t]*[\"']?(?P<token>[A-Za-z0-9+/_=.-]{20,})")
INTEGRITY_KEY_RE = re.compile(r"(?i)hash|digest|sha\d*|checksum|uuid|guid|commit|fingerprint|etag"
                              r"|image|version|ref")


def _shannon(text: str) -> float:
    counts = Counter(text)
    return -sum(n / len(text) * math.log2(n / len(text)) for n in counts.values())


def high_entropy(text: str) -> list[Hit]:
    """Long random-looking values next to a key that no rule redacted: worth a human look."""
    hits = set()
    for match in ENTROPY_RE.finditer(text):
        token = match.group("token")
        if INTEGRITY_KEY_RE.search(match.group("key")) or re.fullmatch(r"[0-9a-fA-F.-]+", token):
            continue
        if not (re.search(r"[a-z]", token) and re.search(r"[A-Z]", token) and re.search(r"\d", token)):
            continue
        if _shannon(token) >= 3.5:
            hits.add(Hit(text.count("\n", 0, match.start("token")) + 1, "entropy", "secret"))
    return sorted(hits, key=lambda hit: hit.line)


ENV_LINE_RE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")
# `.env.local` holds local secrets, so every value is one, except where the variable's
# name says it is a location, a name or a number (NAS_HOST, BACKUP_STORAGE, SSH_PORT...).
NOT_SECRET_NAME_RE = re.compile(
    r"(?i)(?:^|_)(?:HOST|HOSTNAME|USER|USERNAME|PORT|DIR|PATH|FILE|STORAGE|NODES?|PCT|DAYS|ID"
    r"|NAME|URL|DOMAIN|EMAIL|TZ|LANG)$|^(?:LOG|ASSUME)_")


def env_values(path: Path | None) -> dict[str, str]:
    if path is None or not Path(path).is_file():
        return {}
    values = {}
    for raw in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        if raw.lstrip().startswith("#"):
            continue
        match = ENV_LINE_RE.match(raw)
        if not match:
            continue
        value = match.group(2)
        if value and value[0] in "\"'":
            end = value.find(value[0], 1)          # quoted: up to the closing quote
            value = value[1:end] if end > 0 else value[1:]
        else:
            value = re.split(r"[ \t]+#", value, maxsplit=1)[0].strip()   # drop ` # comment`
        values[match.group(1)] = value
    return values


def load_env_literals(path: Path | None) -> list[str]:
    """Values (≥ 6 chars) of `.env.local` variables whose names do not mark them public."""
    return [value for name, value in env_values(path).items()
            if len(value) >= 6 and not NOT_SECRET_NAME_RE.search(name)]


def env_public_values(path: Path | None) -> dict[str, str]:
    """The `.env.local` values deliberately not redacted, so capture can say when one shows up."""
    return {name: value for name, value in env_values(path).items()
            if len(value) >= 6 and NOT_SECRET_NAME_RE.search(name)}


class PatternError(ValueError):
    def __init__(self, line: int, message: str):
        super().__init__(f"line {line}: {message}")
        self.line = line


def load_custom_patterns(path: Path) -> list[re.Pattern]:
    """One regex per line; blank lines and # comments ignored."""
    if not Path(path).is_file():
        return []
    patterns = []
    for number, raw in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        text = raw.strip()
        if not text or text.startswith("#"):
            continue
        try:
            patterns.append(re.compile(text))
        except re.error as exc:
            raise PatternError(number, f"invalid regex {text!r}: {exc}") from exc
    return patterns
