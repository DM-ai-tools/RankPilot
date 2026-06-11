"""Ahrefs API v3 — Keywords Explorer (live volume, KD, traffic potential)."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import HTTPException, status

from app.core.config import Settings, get_ahrefs_api_key

logger = logging.getLogger(__name__)

_BASE = "https://api.ahrefs.com/v3"
# Batch suburb/rank lookups — no history (Ahrefs requires date range if history is requested).
_OVERVIEW_SELECT_BASIC = "keyword,volume,difficulty,traffic_potential,cpc,global_volume,volume_monthly"
_OVERVIEW_SELECT_WITH_HISTORY = f"{_OVERVIEW_SELECT_BASIC},volume_monthly_history"
_MATCHING_SELECT = "keyword,volume,difficulty,traffic_potential,cpc,global_volume"


def difficulty_label(kd: int | None) -> str | None:
    if kd is None:
        return None
    if kd <= 10:
        return "Easy"
    if kd <= 30:
        return "Medium"
    if kd <= 50:
        return "Hard"
    return "Very Hard"


def format_volume_display(volume: int | None, *, global_volume: int | None = None) -> str:
    """Ahrefs-style volume label (e.g. 0–10 for very low searches)."""
    v = volume if volume is not None else None
    g = global_volume if global_volume is not None else None
    if v is None or v == 0:
        if g is not None and 0 < g <= 10:
            return "0–10"
        return "0" if (v == 0 or v is None) and (g is None or g == 0) else "0–10"
    if v < 10:
        return "0–10"
    if v < 1000:
        return str(v)
    return f"{v:,}"


def kd_short_label(kd: int | None) -> str:
    if kd is None:
        return "N/A"
    label = difficulty_label(kd) or ""
    return f"{kd} {label}" if label else str(kd)


def opportunity_score(volume: int | None, difficulty: int | None, traffic_potential: int | None = None) -> int:
    """Higher = more volume relative to ranking difficulty (Ahrefs-style opportunity)."""
    if traffic_potential and traffic_potential > 0:
        base = traffic_potential
    else:
        base = max(0, int(volume or 0))
    kd = 50 if difficulty is None else max(0, min(100, int(difficulty)))
    return int(base * (100 - kd) / 100)


class AhrefsClient:
    def __init__(self, settings: Settings | None = None) -> None:
        key = get_ahrefs_api_key()
        if not key:
            raise ValueError("AHREFS_API_KEY is not set")
        self._api_key = key
        self._http = httpx.AsyncClient(timeout=60.0)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        url = f"{_BASE}/{path.lstrip('/')}"
        resp = await self._http.get(
            url,
            params=params,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Accept": "application/json",
            },
        )
        if resp.status_code == 401:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Ahrefs API key rejected (401). Check AHREFS_API_KEY in backend/.env.",
            )
        if resp.status_code == 403:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Ahrefs API access denied (403). Your plan may not include this endpoint.",
            )
        if resp.status_code == 429:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Ahrefs rate limit — wait a minute and try again.",
            )
        if not resp.is_success:
            detail = resp.text[:400]
            with __import__("contextlib").suppress(Exception):
                detail = str(resp.json().get("error") or detail)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Ahrefs API error ({resp.status_code}): {detail}",
            )
        data = resp.json()
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
        kw = str(row.get("keyword") or "").strip()
        vol = row.get("volume")
        gv = row.get("global_volume")
        kd = row.get("difficulty")
        tp = row.get("traffic_potential")
        cpc = row.get("cpc")
        try:
            volume = int(vol) if vol is not None else None
        except (TypeError, ValueError):
            volume = None
        try:
            global_volume = int(gv) if gv is not None else None
        except (TypeError, ValueError):
            global_volume = None
        try:
            difficulty = int(kd) if kd is not None else None
        except (TypeError, ValueError):
            difficulty = None
        try:
            traffic_potential = int(tp) if tp is not None else None
        except (TypeError, ValueError):
            traffic_potential = None
        try:
            cpc_cents = int(cpc) if cpc is not None else None
        except (TypeError, ValueError):
            cpc_cents = None
        vol_int = volume if volume is not None else 0
        opp = opportunity_score(vol_int or global_volume, difficulty, traffic_potential)
        history = row.get("volume_monthly_history")
        if not isinstance(history, list):
            history = []
        return {
            "keyword": kw,
            "volume": volume,
            "volume_display": format_volume_display(volume, global_volume=global_volume),
            "global_volume": global_volume,
            "difficulty": difficulty,
            "traffic_potential": traffic_potential,
            "cpc_cents": cpc_cents,
            "competition": difficulty_label(difficulty),
            "opportunity_score": opp,
            "volume_monthly_history": history,
        }

    async def keywords_overview(
        self,
        keywords: list[str],
        *,
        country: str = "au",
    ) -> list[dict[str, Any]]:
        cleaned = [k.strip() for k in keywords if k and k.strip()]
        if not cleaned:
            return []
        # Ahrefs accepts comma-separated keywords in one request (min 50 API units).
        unique: list[str] = []
        seen: set[str] = set()
        for k in cleaned:
            low = k.lower()
            if low in seen:
                continue
            seen.add(low)
            unique.append(k)
        out: list[dict[str, Any]] = []
        chunk_size = 40
        for i in range(0, len(unique), chunk_size):
            chunk = unique[i : i + chunk_size]
            data = await self._get(
                "keywords-explorer/overview",
                {
                    "country": country,
                    "keywords": ",".join(chunk),
                    "select": _OVERVIEW_SELECT_BASIC,
                },
            )
            rows = data.get("keywords") or []
            if isinstance(rows, list):
                for row in rows:
                    if isinstance(row, dict):
                        out.append(self._normalize_row(row))
        return out

    async def keyword_overview_one(
        self,
        keyword: str,
        *,
        country: str = "au",
        include_history: bool = True,
    ) -> dict[str, Any]:
        keyword = (keyword or "").strip()
        if not keyword:
            return {}
        from datetime import date, timedelta

        params: dict[str, Any] = {
            "country": country,
            "keywords": keyword,
            "select": _OVERVIEW_SELECT_WITH_HISTORY if include_history else _OVERVIEW_SELECT_BASIC,
        }
        if include_history:
            end = date.today()
            start = end - timedelta(days=365)
            params["volume_monthly_date_from"] = start.isoformat()
            params["volume_monthly_date_to"] = end.isoformat()
        data = await self._get("keywords-explorer/overview", params)
        rows = data.get("keywords") or []
        if isinstance(rows, list) and rows and isinstance(rows[0], dict):
            return self._normalize_row(rows[0])
        return self._normalize_row({"keyword": keyword})

    async def matching_terms(
        self,
        seed: str,
        *,
        country: str = "au",
        limit: int = 30,
        terms: str = "all",
    ) -> list[dict[str, Any]]:
        seed = (seed or "").strip()
        if not seed:
            return []
        params: dict[str, Any] = {
            "country": country,
            "keywords": seed,
            "select": _MATCHING_SELECT,
            "limit": max(5, min(int(limit), 100)),
            "order_by": "volume:desc",
            "match_mode": "terms",
        }
        if terms == "questions":
            params["terms"] = "questions"
        data = await self._get("keywords-explorer/matching-terms", params)
        return self._rows_to_normalized(data)

    async def related_terms(
        self,
        seed: str,
        *,
        country: str = "au",
        limit: int = 20,
        terms: str = "also_rank_for",
    ) -> list[dict[str, Any]]:
        seed = (seed or "").strip()
        if not seed:
            return []
        data = await self._get(
            "keywords-explorer/related-terms",
            {
                "country": country,
                "keywords": seed,
                "select": _MATCHING_SELECT,
                "limit": max(5, min(int(limit), 50)),
                "order_by": "volume:desc",
                "terms": terms,
                "view_for": "top_10",
            },
        )
        return self._rows_to_normalized(data)

    async def search_suggestions(
        self,
        seed: str,
        *,
        country: str = "au",
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        seed = (seed or "").strip()
        if not seed:
            return []
        data = await self._get(
            "keywords-explorer/search-suggestions",
            {
                "country": country,
                "keywords": seed,
                "select": _MATCHING_SELECT,
                "limit": max(5, min(int(limit), 50)),
                "order_by": "volume:desc",
            },
        )
        return self._rows_to_normalized(data)

    def _rows_to_normalized(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        rows = data.get("keywords") or []
        out: list[dict[str, Any]] = []
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict):
                    out.append(self._normalize_row(row))
        return out

    async def serp_overview(
        self,
        keyword: str,
        *,
        country: str = "au",
        top_positions: int = 10,
    ) -> list[dict[str, Any]]:
        """Top organic Google results for a keyword (who ranks for it)."""
        keyword = (keyword or "").strip()
        if not keyword:
            return []
        data = await self._get(
            "serp-overview/serp-overview",
            {
                "keyword": keyword,
                "country": country.strip().lower()[:2],
                "select": "position,url,title,type,traffic",
                "top_positions": max(3, min(int(top_positions), 20)),
            },
        )
        rows = data.get("positions") or []
        out: list[dict[str, Any]] = []
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                kinds = row.get("type")
                kinds = [str(k) for k in kinds] if isinstance(kinds, list) else []
                # Organic results + Google Maps local pack; skip ads and SERP widgets.
                if kinds and "organic" not in kinds and "local_pack" not in kinds:
                    continue
                url = str(row.get("url") or "").strip()
                if not url:
                    continue
                pos = row.get("position")
                try:
                    position = int(pos) if pos is not None else None
                except (TypeError, ValueError):
                    position = None
                traffic = row.get("traffic")
                try:
                    traffic_int = int(traffic) if traffic is not None else None
                except (TypeError, ValueError):
                    traffic_int = None
                out.append(
                    {
                        "position": position,
                        "url": url,
                        "title": str(row.get("title") or "") or None,
                        "traffic": traffic_int,
                        "types": kinds,
                    }
                )
        return out

    async def site_organic_keywords(
        self,
        target: str,
        *,
        country: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Site Explorer — organic keywords a competitor domain ranks for."""
        target = (target or "").strip()
        if not target:
            return []
        from datetime import date

        params: dict[str, Any] = {
            "target": target,
            "date": date.today().isoformat(),
            "select": "keyword,volume,keyword_difficulty,best_position,sum_traffic,cpc,best_position_url",
            "limit": max(10, min(int(limit), 200)),
            "order_by": "sum_traffic:desc",
            "mode": "subdomains",
        }
        if country:
            params["country"] = country.strip().lower()[:2]
        data = await self._get("site-explorer/organic-keywords", params)
        rows = data.get("keywords") or []
        out: list[dict[str, Any]] = []
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                normalized = self._normalize_row(
                    {
                        "keyword": row.get("keyword"),
                        "volume": row.get("volume"),
                        "difficulty": row.get("keyword_difficulty"),
                        "traffic_potential": row.get("sum_traffic"),
                        "cpc": row.get("cpc"),
                    }
                )
                pos = row.get("best_position")
                try:
                    normalized["best_position"] = int(pos) if pos is not None else None
                except (TypeError, ValueError):
                    normalized["best_position"] = None
                traffic = row.get("sum_traffic")
                try:
                    normalized["traffic"] = int(traffic) if traffic is not None else None
                except (TypeError, ValueError):
                    normalized["traffic"] = None
                normalized["ranking_url"] = str(row.get("best_position_url") or "") or None
                if normalized["keyword"]:
                    out.append(normalized)
        return out
