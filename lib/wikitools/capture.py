"""wiki-capture: redact command output and store it as immutable evidence under <wiki>/raw/."""
from __future__ import annotations

import argparse
import datetime
import re
import sys
from pathlib import Path

from . import frontmatter, redact
from .config import SOURCE_TYPES, ConfigError, load_config
from .encoding import EncodingError, decode
from .util import SLUG_RE, harness_root, parse_date, short_hash

EXIT_OK, EXIT_USAGE, EXIT_IMMUTABLE, EXIT_EMPTY = 0, 1, 2, 3
LARGE_BYTES = 1024 * 1024

STUB_BODY = """
## Summary

TODO(ingest)

## Key points

TODO(ingest)

## Entities mentioned

TODO(ingest)

## Concepts mentioned

TODO(ingest)
"""

REVERIFY_BODY = """
## Summary

TODO(ingest): re-verification. The state on {date} is identical to the evidence in `{raw}`;
record it in the entity's update history and set `last_verified: {date}`.

## Key points

TODO(ingest)
"""


class _Parser(argparse.ArgumentParser):
    """argparse exits 2 on usage errors, but 2 means an immutability conflict here."""

    def error(self, message: str):  # type: ignore[override]
        self.print_usage(sys.stderr)
        print(f"{self.prog}: error: {message}", file=sys.stderr)
        sys.exit(EXIT_USAGE)


def _fail(message: str, code: int = EXIT_USAGE) -> int:
    print(f"wiki-capture: {message}", file=sys.stderr)
    return code


def _note(message: str) -> None:
    print(f"wiki-capture: {message}", file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog="wiki-capture",
        description="Redact command output (stdin or --file) and store it as evidence in "
                    "<wiki>/raw/, with a source stub in <wiki>/sources/.")
    parser.add_argument("slug", help="kebab-case name, e.g. pve1-versions")
    parser.add_argument("--file", type=Path, help="read this file instead of stdin")
    parser.add_argument("--origin", help='where the output came from, e.g. "pveversion -v @ pve1"')
    parser.add_argument("--trust", default="measured", help="trust_level (default: measured)")
    parser.add_argument("--type", dest="source_type", default="measurement",
                        help="source type (default: measurement)")
    parser.add_argument("--title", help="source title (default: derived from the slug)")
    parser.add_argument("--date", help="evidence date YYYY-MM-DD (default: today)")
    parser.add_argument("--wiki", type=Path, help="wiki root (default: <harness>/wiki)")
    parser.add_argument("--dry-run", action="store_true", help="print the redacted output; write nothing")
    parser.add_argument("--env-file", type=Path,
                        help="file whose secret values are redacted (default: <harness>/.env.local)")
    parser.add_argument("--encoding", help="decode the input with this codec instead of detecting it")
    parser.add_argument("--keep", action="append", default=[], metavar="REGEX",
                        help="exposure: public only: never replace text matching REGEX "
                             "(e.g. an unlabeled version number); repeatable")
    return parser


def _read_bytes(args) -> bytes | None:
    if args.file is not None:
        return args.file.read_bytes()
    if sys.stdin.isatty():
        return None
    if hasattr(sys.stdin, "buffer"):  # bytes keep CRLF exactly as the tool printed it
        return sys.stdin.buffer.read()
    return sys.stdin.read().encode("utf-8")


def _stored_hash(source_path: Path) -> str | None:
    fm, _, _ = frontmatter.split(source_path.read_text(encoding="utf-8", errors="replace"))
    try:
        return frontmatter.parse(fm).get("source_hash") if fm is not None else None
    except frontmatter.FrontmatterError:
        return None


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not SLUG_RE.match(args.slug):
        return _fail(f"slug must be kebab-case (a-z, 0-9, single dashes): {args.slug!r}")
    date = args.date or datetime.date.today().isoformat()
    if parse_date(date) is None:
        return _fail(f"--date must be YYYY-MM-DD: {date!r}")
    wiki = args.wiki or harness_root() / "wiki"
    try:
        config = load_config(wiki)
    except ConfigError as exc:
        return _fail(str(exc))
    if args.trust not in config.trust_levels:
        return _fail(f"--trust must be one of: {', '.join(config.trust_levels)}")
    if args.source_type not in SOURCE_TYPES:
        return _fail(f"--type must be one of: {', '.join(SOURCE_TYPES)}")
    if args.file is not None and not args.file.is_file():
        return _fail(f"--file {args.file} not found")
    try:
        keep = [re.compile(pattern) for pattern in args.keep]
    except re.error as exc:
        return _fail(f"--keep: invalid regex: {exc}")

    data = _read_bytes(args)
    if data is None:
        return _fail("no input: pipe command output in, or pass --file")
    try:
        decoded = decode(data, args.encoding)
    except (EncodingError, LookupError) as exc:
        return _fail(str(exc))
    content = decoded.text
    if not content.strip():
        return _fail("input is empty; nothing captured", EXIT_EMPTY)
    if decoded.encoding != "utf-8" and not args.encoding:
        _note(f"input is not UTF-8; decoded as {decoded.encoding} and stored as UTF-8")
    if len(data) > LARGE_BYTES:
        _note(f"warning: large capture ({len(data) / LARGE_BYTES:.1f} MB): nobody can read it in full "
              "before committing; bound the collector (journalctl --since, tail -n, grep)")

    try:
        custom = redact.load_custom_patterns(wiki / ".capture-patterns")
    except redact.PatternError as exc:
        return _fail(f"{wiki / '.capture-patterns'}: {exc}")
    env_file = args.env_file or harness_root() / ".env.local"
    literals = redact.load_env_literals(env_file)
    result = redact.redact(content, literals, custom, config.exposure, keep)
    totals = dict(result.counts)
    fields = {}
    for key, value in (("title", args.title), ("origin", args.origin)):
        if value:  # written to the source page, so redacted like the content
            cleaned = redact.redact(value, literals, custom, config.exposure, keep)
            fields[key] = cleaned.text
            for bucket, count in cleaned.counts.items():
                totals[bucket] += count
    counts = " ".join(f"{key}={value}" for key, value in totals.items())

    public = [name for name, value in redact.env_public_values(env_file).items() if value in result.text]
    if public:
        _note(f"note: values of {', '.join(public)} from .env.local appear in the output and are "
              "not redacted (their names mark them as not secret)")
    entropy = redact.high_entropy(result.text)
    if entropy:
        lines = ", ".join(str(hit.line) for hit in entropy)
        _note(f"warning: {len(entropy)} random-looking value(s) next to a key were not redacted "
              f"(line {lines}): review them before committing")

    if args.dry_run:
        sys.stdout.write(result.text if result.text.endswith("\n") else result.text + "\n")
        print(f"--- redactions: {counts}")
        return EXIT_OK

    stored = result.text.encode("utf-8")
    digest = short_hash(stored)
    raw_dir = wiki / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    name = f"{date}-{args.slug}"
    source_path = wiki / "sources" / f"{name}.md"
    meta = {
        "title": fields.get("title") or args.slug.replace("-", " ").capitalize(),
        "date": date,
        "type": args.source_type,
        "source": f"raw/{name}.txt",
        "source_hash": digest,
        "trust_level": args.trust,
    }
    if "origin" in fields:
        meta["origin"] = fields["origin"]
    if decoded.encoding != "utf-8":
        meta["encoding"] = decoded.encoding
    meta["redactions"] = totals

    for existing in sorted(raw_dir.iterdir()):
        if (existing.is_file() and existing.name != ".gitkeep"
                and short_hash(existing.read_bytes()) == digest):
            print(f"unchanged: {existing}")
            raw_rel = f"raw/{existing.name}"
            if not source_path.exists() and raw_rel != meta["source"]:
                # Re-verification: the evidence exists; the observation today gets a dated source.
                meta["source"] = raw_rel
                source_path.parent.mkdir(parents=True, exist_ok=True)
                source_path.write_text(frontmatter.dumps(meta) + REVERIFY_BODY.format(date=date, raw=raw_rel),
                                       encoding="utf-8")
                print(f"source: {source_path}")
                print("  identical evidence: this source records today's observation of it; "
                      "cite it, and update the entity's update history and last_verified")
            else:
                print("  identical evidence already exists: cite it")
            return EXIT_OK

    raw_path = raw_dir / f"{name}.txt"
    if raw_path.exists():
        return _fail(f"{raw_path} exists with different content; raw/ is immutable, "
                     "choose another slug", EXIT_IMMUTABLE)
    if source_path.exists() and _stored_hash(source_path) not in (None, digest):
        return _fail(f"{source_path} is stale: it describes different evidence than this capture; "
                     "delete or update it first", EXIT_IMMUTABLE)
    try:
        with open(raw_path, "xb") as handle:
            handle.write(stored)
    except FileExistsError:
        return _fail(f"{raw_path} exists with different content; raw/ is immutable, "
                     "choose another slug", EXIT_IMMUTABLE)

    if not source_path.exists():
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_text(frontmatter.dumps(meta) + STUB_BODY, encoding="utf-8")

    print(f"raw: {raw_path}")
    print(f"source: {source_path}")
    print(f"hash: {digest}")
    print(f"redactions: {counts}")
    return EXIT_OK
