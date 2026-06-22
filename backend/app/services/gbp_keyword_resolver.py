"""Resolve which Ahrefs keyword a GBP post was targeting."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.lib.keyword_match import match_keyword_from_post_body
from app.lib.primary_keywords import parse_primary_keywords


async def get_gbp_keyword_candidates(session: AsyncSession, client_id: UUID) -> list[str]:
    """Profile keywords + keyword-tracker history (published posts first)."""
    row = (
        await session.execute(
            text("SELECT primary_keyword FROM rp_clients WHERE client_id = :cid LIMIT 1"),
            {"cid": str(client_id)},
        )
    ).mappings().first()
    client_keywords = parse_primary_keywords(str((row or {}).get("primary_keyword") or ""))

    tracked_rows = (
        await session.execute(
            text(
                """
                SELECT keyword
                FROM rp_keyword_tracker
                WHERE client_id = :cid
                ORDER BY
                  CASE source
                    WHEN 'gbp_post_published' THEN 0
                    WHEN 'gbp_post' THEN 1
                    ELSE 2
                  END,
                  added_at DESC
                """
            ),
            {"cid": str(client_id)},
        )
    ).mappings().all()

    seen: set[str] = set()
    ordered: list[str] = []
    for kw in [str(r["keyword"]) for r in tracked_rows] + client_keywords:
        key = kw.strip().lower()
        if key and key not in seen:
            seen.add(key)
            ordered.append(kw.strip())
    return ordered


def resolve_gbp_post_target_keyword(
    payload: dict,
    candidates: list[str],
    *,
    post_index: int = 0,
) -> str:
    """Best keyword for a GBP post — stored value, body match, then profile fallback."""
    body = str(payload.get("body") or "").strip()
    stored = str(payload.get("target_keyword") or "").strip()
    imported = bool(payload.get("imported_from_google"))

    # RankPilot-generated posts: trust stored keyword unless clearly wrong.
    if stored and not imported:
        return stored.split(",")[0].strip()

    # Google imports: infer from post text + keyword history (stored value is often a guess).
    if candidates and body:
        matched = match_keyword_from_post_body(body, candidates)
        if matched:
            return matched

    if stored and "," not in stored:
        return stored

    keywords_used = payload.get("keywords_used")
    if isinstance(keywords_used, list):
        for item in keywords_used:
            s = str(item or "").strip()
            if s:
                return s.split(",")[0].strip()
    elif isinstance(keywords_used, str) and keywords_used.strip():
        return keywords_used.split(",")[0].strip()

    tags = payload.get("tags")
    target_area = str(payload.get("target_area") or "").strip().lower()
    if isinstance(tags, list):
        for tag in tags:
            t = str(tag or "").strip()
            if not t or t.upper() == "STANDARD":
                continue
            if target_area and t.lower() in target_area:
                continue
            return t

    profile_only = parse_primary_keywords(", ".join(candidates))
    if profile_only:
        return profile_only[post_index % len(profile_only)]
    return ""
