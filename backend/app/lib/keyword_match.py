"""Match GBP post body text to the most likely target keyword."""

from __future__ import annotations

import re

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall((text or "").lower()) if len(t) > 2]


def match_keyword_from_post_body(body: str, candidates: list[str]) -> str:
    """Pick the candidate keyword that best matches post content (phrase + token overlap)."""
    body_low = (body or "").lower()
    if not body_low or not candidates:
        return ""

    body_token_set = set(_tokens(body_low))
    best_kw = ""
    best_score = 0.0

    for kw in candidates:
        candidate = (kw or "").strip()
        if not candidate:
            continue
        kw_low = candidate.lower()

        if kw_low in body_low:
            score = 100.0 + len(kw_low)
        else:
            kw_tokens = _tokens(kw_low)
            if not kw_tokens:
                continue
            matched = sum(1 for t in kw_tokens if t in body_token_set)
            score = (matched / len(kw_tokens)) * 60.0
            # Prefer longer / more specific keywords when overlap is equal.
            score += min(len(kw_tokens), 6) * 0.5

        if score > best_score:
            best_score = score
            best_kw = candidate

    # Require at least ~40% token overlap, or a full phrase match (score >= 100).
    if best_score < 24.0:
        return ""
    return best_kw
