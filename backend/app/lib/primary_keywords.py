"""Parse comma-separated primary service keywords from onboarding / profile."""

from __future__ import annotations

import re

_SPLIT_RE = re.compile(r"[,;\n]+")


def parse_primary_keywords(raw: str) -> list[str]:
    """Split comma/semicolon/newline-separated keywords; trim and dedupe."""
    out: list[str] = []
    seen: set[str] = set()
    for part in _SPLIT_RE.split(raw or ""):
        s = re.sub(r"\s+", " ", part.strip())
        if len(s) < 2:
            continue
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


def normalize_primary_keywords(raw: str) -> str:
    """Canonical comma-separated storage form."""
    return ", ".join(parse_primary_keywords(raw))


def scan_keyword_from_primary(raw: str) -> str:
    """First keyword — used for Maps rank scans and rank history joins."""
    parsed = parse_primary_keywords(raw)
    if parsed:
        return parsed[0]
    return (raw or "").strip()
