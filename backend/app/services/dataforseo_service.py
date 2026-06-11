"""DataForSEO HTTP client — Maps (Local Pack) rank checking.

Maps scan flow:
  1. POST /v3/serp/google/maps/task_post  → get task_id
  2. Poll GET /v3/serp/google/maps/task_get/advanced/{task_id} until status 20000
  3. Match domain in `items` to find rank position
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import UTC, datetime
from urllib.parse import urlparse

import httpx

from app.core.config import Settings
from app.lib.maps_pack_rank import infer_maps_pack_rank

logger = logging.getLogger(__name__)

_BASE = "https://api.dataforseo.com/v3"
# Polling: short sleeps early (tasks often finish within ~15s), then back off.
_POLL_FAST_S = 2
_POLL_INTERVAL_S = 5
_POLL_FAST_ATTEMPTS = 8
_MAX_POLLS = 12  # ~1 min worst-case per task
_MAX_REVIEWS_POLLS = 24  # Business Data reviews queue can take 60–90s
_TASK_GET_HTTP_RETRIES = 5  # retry transient 5xx / network on task_get
_MIN_MAPS_ITEMS_TO_STOP = 3  # stop widening zoom once we have a usable local pack

# DataForSEO location_name uses full region names, comma-separated, no spaces
# (see https://docs.dataforseo.com/v3/serp/google/locations/ — e.g. "Alabama,United States").
_AU_STATE_FULL: dict[str, str] = {
    "VIC": "Victoria",
    "NSW": "New South Wales",
    "QLD": "Queensland",
    "SA": "South Australia",
    "WA": "Western Australia",
    "TAS": "Tasmania",
    "NT": "Northern Territory",
    "ACT": "Australian Capital Territory",
}


def format_maps_location_name(suburb: str, state_abbr: str) -> str:
    """Human-readable AU place string (suburb + state + country) for logs and UI context."""
    s = (suburb or "").strip()
    st = (state_abbr or "").strip().upper()
    country = "Australia"
    if st in _AU_STATE_FULL:
        return f"{s},{_AU_STATE_FULL[st]},{country}"
    if st:
        return f"{s},{st},{country}"
    return f"{s},{country}"


def _serp_location_coordinate(lat: float, lng: float, zoom: int = 17) -> str:
    """Maps API: latitude,longitude,zoom — max 7 decimals per docs."""
    la = round(float(lat), 7)
    lo = round(float(lng), 7)
    z = max(3, min(21, int(zoom)))
    return f"{la},{lo},{z}z"


def _state_location_name(state_abbr: str) -> str:
    st = (state_abbr or "").strip().upper()
    full = _AU_STATE_FULL.get(st, st)
    return f"{full},Australia" if full else "Australia"


def _domain(url: str) -> str:
    """Normalise URL → bare domain for comparison (strip www.)."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    host = urlparse(url).netloc.lower()
    return re.sub(r"^www\.", "", host)


def _brand_hint_from_url(url: str) -> str:
    """clicktrends.com.au -> clicktrends"""
    d = _domain(url)
    if not d:
        return ""
    return (d.split(".")[0] or "").replace("-", " ").strip().lower()


class DataForSEOClient:
    """Reuses one HTTP connection pool per scan job (avoid TLS + TCP setup on every SERP call)."""

    def __init__(self, settings: Settings):
        self._auth = (settings.dataforseo_login, settings.dataforseo_password)
        self._http_client: httpx.AsyncClient | None = None

    def _http(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                auth=self._auth,
                timeout=httpx.Timeout(30.0, connect=15.0),
                limits=httpx.Limits(max_connections=48, max_keepalive_connections=24),
            )
        return self._http_client

    async def aclose(self) -> None:
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    def _poll_sleep_s(self, attempt: int) -> float:
        return float(_POLL_FAST_S if attempt < _POLL_FAST_ATTEMPTS else _POLL_INTERVAL_S)

    # ------------------------------------------------------------------ #
    # Public: get position for one keyword+suburb combo                   #
    # ------------------------------------------------------------------ #

    async def get_maps_rank_with_serp(
        self,
        keyword: str,
        location: str,
        business_url: str,
        business_name: str | None = None,
        language_code: str = "en",
        *,
        lat: float | None = None,
        lng: float | None = None,
    ) -> tuple[int | None, list[dict]]:
        """Return (rank, serp_items) from Google Maps SERP via DataForSEO.

        `serp_items` is the item list from the same task pass that yielded `rank`, or the last
        non-empty SERP if the business never matched (still useful for competitor pins).
        """
        if lat is None or lng is None:
            logger.warning(
                "maps rank skipped: missing lat/lng (%s) — Maps task_post requires location_coordinate",
                location or keyword,
            )
            return None, []

        zoom_steps: list[tuple[int, bool | None]] = [
            (17, None),
            (13, None),
        ]
        last_nonempty: list[dict] = []
        for zoom, search_places in zoom_steps:
            task_id = await self._post_task(
                keyword,
                location,
                language_code,
                lat=lat,
                lng=lng,
                zoom=zoom,
                search_places=search_places,
            )
            if not task_id:
                continue
            items = await self._poll_task(task_id)
            if items:
                last_nonempty = items
            rank = self._find_rank(items, business_url, business_name=business_name)
            if rank is not None:
                return rank, items
            # Business not in pack but we already have local results — skip wider zoom.
            if len(items) >= _MIN_MAPS_ITEMS_TO_STOP:
                return None, items
        return None, last_nonempty

    async def get_maps_rank(
        self,
        keyword: str,
        location: str,
        business_url: str,
        business_name: str | None = None,
        language_code: str = "en",
        *,
        lat: float | None = None,
        lng: float | None = None,
    ) -> int | None:
        """Return 1-based rank position of business_url in Maps pack, or None if not found."""
        rank, _ = await self.get_maps_rank_with_serp(
            keyword,
            location,
            business_url,
            business_name=business_name,
            language_code=language_code,
            lat=lat,
            lng=lng,
        )
        return rank

    async def get_state_keyword_volume(
        self,
        keyword: str,
        state_abbr: str,
        language_code: str = "en",
    ) -> int | None:
        """Return latest full-month keyword search volume for an AU state."""
        task_id = await self._post_search_volume_task(keyword, state_abbr, language_code)
        if not task_id:
            return None
        items = await self._poll_search_volume_task(task_id)
        if not items:
            return None
        item = items[0]
        monthly = item.get("monthly_searches")
        if isinstance(monthly, list):
            strict_prev = self._pick_exact_previous_month_volume(monthly)
            if strict_prev is not None:
                return strict_prev
        # Keyword Planner-style average for this geo+keyword (often closer to UI than summing old months).
        try:
            agg = int(item["search_volume"]) if item.get("search_volume") is not None else None
        except (TypeError, ValueError):
            agg = None
        if agg is not None:
            return agg
        if isinstance(monthly, list):
            return self._pick_latest_monthly_volume(monthly)
        return None

    async def get_location_keyword_volume(
        self,
        keyword: str,
        location_name: str,
        language_code: str = "en",
    ) -> int | None:
        """Return latest full-month keyword volume for a specific location string."""
        task_id = await self._post_search_volume_task_for_location(
            keyword,
            location_name,
            language_code,
        )
        if not task_id:
            return None
        items = await self._poll_search_volume_task(task_id)
        if not items:
            return None
        return self._volume_from_search_item(items[0])

    async def get_search_volumes_live(
        self,
        keywords: list[str],
        state_abbr: str,
        language_code: str = "en",
    ) -> list[dict[str, object]]:
        """Live Google Ads search volumes for many keywords at AU state geo."""
        kws = [re.sub(r"\s+", " ", (k or "").strip()) for k in keywords if (k or "").strip()]
        if not kws:
            return []
        location_name = _state_location_name(state_abbr)
        task = {
            "keywords": kws[:700],
            "location_name": location_name,
            "language_code": language_code,
        }
        c = self._http()
        try:
            r = await c.post(f"{_BASE}/keywords_data/google_ads/search_volume/live", json=[task])
            r.raise_for_status()
            return self._parse_live_keyword_rows(r.json())
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in (402, 403, 404):
                raise
            logger.info("DataForSEO search_volume/live unavailable (%s), using task API", exc.response.status_code)
            return await self.get_search_volumes_batch(kws, state_abbr, language_code=language_code)

    async def get_search_volumes_batch(
        self,
        keywords: list[str],
        state_abbr: str,
        language_code: str = "en",
    ) -> list[dict[str, object]]:
        """Task-based search volumes (same API as Maps scans)."""
        kws = [re.sub(r"\s+", " ", (k or "").strip()) for k in keywords if (k or "").strip()]
        if not kws:
            return []
        task_id = await self._post_search_volume_task_multi(kws[:700], state_abbr, language_code)
        if not task_id:
            return []
        items = await self._poll_search_volume_task(task_id)
        out: list[dict[str, object]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            kw = str(item.get("keyword") or "").strip()
            if not kw:
                continue
            vol = self._volume_from_search_item(item)
            comp = item.get("competition")
            comp_name = comp if isinstance(comp, str) else (comp.name if hasattr(comp, "name") else None)
            out.append(
                {
                    "keyword": kw,
                    "avg_monthly_searches": int(vol or 0),
                    "competition": comp_name,
                    "competition_index": int(item.get("competition_index") or 0),
                }
            )
        return out

    async def get_keywords_for_keywords_live(
        self,
        keywords: list[str],
        state_abbr: str,
        *,
        language_code: str = "en",
        limit: int = 40,
    ) -> list[dict[str, object]]:
        """Live Keyword Planner suggestions for seed keyword(s) at AU state geo."""
        seeds = [re.sub(r"\s+", " ", (k or "").strip()) for k in keywords if (k or "").strip()]
        if not seeds:
            return []
        task = {
            "keywords": seeds[:10],
            "location_name": _state_location_name(state_abbr),
            "language_code": language_code,
        }
        c = self._http()
        try:
            r = await c.post(f"{_BASE}/keywords_data/google_ads/keywords_for_keywords/live", json=[task])
            r.raise_for_status()
            rows = self._parse_live_keyword_rows(r.json())
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in (402, 403, 404):
                raise
            logger.info(
                "DataForSEO keywords_for_keywords/live unavailable (%s), using task API",
                exc.response.status_code,
            )
            rows = await self.get_keywords_for_keywords_batch(seeds, state_abbr, language_code=language_code)
        rows.sort(key=lambda x: int(x.get("avg_monthly_searches") or 0), reverse=True)
        return rows[: max(5, min(limit, 100))]

    async def get_keywords_for_keywords_batch(
        self,
        keywords: list[str],
        state_abbr: str,
        language_code: str = "en",
    ) -> list[dict[str, object]]:
        seeds = [re.sub(r"\s+", " ", (k or "").strip()) for k in keywords if (k or "").strip()]
        if not seeds:
            return []
        task_id = await self._post_keywords_for_keywords_task(seeds[:10], state_abbr, language_code)
        if not task_id:
            return []
        items = await self._poll_keywords_for_keywords_task(task_id)
        out: list[dict[str, object]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            kw = str(item.get("keyword") or "").strip()
            if not kw:
                continue
            vol = self._volume_from_search_item(item)
            comp = item.get("competition")
            comp_name = comp if isinstance(comp, str) else (comp.name if hasattr(comp, "name") else None)
            out.append(
                {
                    "keyword": kw,
                    "avg_monthly_searches": int(vol or 0),
                    "competition": comp_name,
                    "competition_index": int(item.get("competition_index") or 0),
                }
            )
        return out

    def _volume_from_search_item(self, item: dict) -> int | None:
        monthly = item.get("monthly_searches")
        if isinstance(monthly, list):
            strict_prev = self._pick_exact_previous_month_volume(monthly)
            if strict_prev is not None:
                return strict_prev
        try:
            agg = int(item["search_volume"]) if item.get("search_volume") is not None else None
        except (TypeError, ValueError):
            agg = None
        if agg is not None:
            return agg
        if isinstance(monthly, list):
            return self._pick_latest_monthly_volume(monthly)
        return None

    def _parse_live_keyword_rows(self, data: dict) -> list[dict[str, object]]:
        tasks = (data.get("tasks") or [{}])[0]
        code = tasks.get("status_code")
        if code != 20000:
            logger.warning(
                "DataForSEO live keywords status %s: %s",
                code,
                tasks.get("status_message"),
            )
            return []
        result = tasks.get("result") or []
        if not isinstance(result, list):
            return []
        out: list[dict[str, object]] = []
        for item in result:
            if not isinstance(item, dict):
                continue
            kw = str(item.get("keyword") or "").strip()
            if not kw:
                continue
            vol = self._volume_from_search_item(item)
            comp = item.get("competition")
            comp_name = comp.name if hasattr(comp, "name") else (str(comp) if comp else None)
            out.append(
                {
                    "keyword": kw,
                    "avg_monthly_searches": int(vol or 0),
                    "competition": comp_name,
                    "competition_index": int(item.get("competition_index") or 0),
                }
            )
        return out

    # ------------------------------------------------------------------ #
    # Internal                                                             #
    # ------------------------------------------------------------------ #

    async def _post_task(
        self,
        keyword: str,
        location: str,
        language_code: str,
        *,
        lat: float,
        lng: float,
        zoom: int = 17,
        search_places: bool | None = None,
    ) -> str | None:
        # Docs: https://docs.dataforseo.com/v3/serp/google/maps/task_post/
        # Use location_coordinate — sending location_name triggers 40501 Invalid Field on Maps task_post.
        task: dict = {
            "keyword": keyword,
            "language_code": language_code,
            "device": "desktop",
            "os": "windows",
            "location_coordinate": _serp_location_coordinate(lat, lng, zoom=zoom),
        }
        if search_places is not None:
            task["search_places"] = search_places

        c = self._http()
        r = await c.post(f"{_BASE}/serp/google/maps/task_post", json=[task])
        r.raise_for_status()
        data = r.json()
        tasks = (data.get("tasks") or [{}])[0]
        sc = tasks.get("status_code")
        if sc != 20100:
            logger.warning(
                "DataForSEO task_post task status %s: %s (keyword=%s location=%s)",
                sc,
                tasks.get("status_message"),
                (keyword or "")[:120],
                (location or "")[:120],
            )
            return None
        tid = tasks.get("id")
        if not tid:
            logger.warning("DataForSEO task_post missing tasks[0].id: %s", data)
            return None
        return str(tid)

    async def _post_search_volume_task(
        self,
        keyword: str,
        state_abbr: str,
        language_code: str,
    ) -> str | None:
        return await self._post_search_volume_task_multi([keyword], state_abbr, language_code)

    async def _post_search_volume_task_multi(
        self,
        keywords: list[str],
        state_abbr: str,
        language_code: str,
    ) -> str | None:
        kws = [k for k in keywords if (k or "").strip()]
        if not kws:
            return None
        task = {
            "keywords": kws,
            "location_name": _state_location_name(state_abbr),
            "language_code": language_code,
        }
        c = self._http()
        r = await c.post(f"{_BASE}/keywords_data/google_ads/search_volume/task_post", json=[task])
        if r.status_code == 402:
            raise httpx.HTTPStatusError(
                "DataForSEO account balance too low for keyword volume API",
                request=r.request,
                response=r,
            )
        r.raise_for_status()
        data = r.json()
        tasks = (data.get("tasks") or [{}])[0]
        sc = tasks.get("status_code")
        if sc != 20100:
            logger.warning(
                "DataForSEO search_volume task_post status %s: %s",
                sc,
                tasks.get("status_message"),
            )
            return None
        tid = tasks.get("id")
        return str(tid) if tid else None

    async def _post_keywords_for_keywords_task(
        self,
        keywords: list[str],
        state_abbr: str,
        language_code: str,
    ) -> str | None:
        kws = [k for k in keywords if (k or "").strip()]
        if not kws:
            return None
        task = {
            "keywords": kws,
            "location_name": _state_location_name(state_abbr),
            "language_code": language_code,
        }
        c = self._http()
        r = await c.post(f"{_BASE}/keywords_data/google_ads/keywords_for_keywords/task_post", json=[task])
        r.raise_for_status()
        data = r.json()
        tasks = (data.get("tasks") or [{}])[0]
        sc = tasks.get("status_code")
        if sc != 20100:
            logger.warning(
                "DataForSEO keywords_for_keywords task_post status %s: %s",
                sc,
                tasks.get("status_message"),
            )
            return None
        tid = tasks.get("id")
        return str(tid) if tid else None

    async def _post_search_volume_task_for_location(
        self,
        keyword: str,
        location_name: str,
        language_code: str,
    ) -> str | None:
        loc = (location_name or "").strip()
        if not loc:
            return None
        task = {
            "keywords": [keyword],
            "location_name": loc,
            "language_code": language_code,
        }
        c = self._http()
        r = await c.post(f"{_BASE}/keywords_data/google_ads/search_volume/task_post", json=[task])
        r.raise_for_status()
        data = r.json()
        tasks = (data.get("tasks") or [{}])[0]
        sc = tasks.get("status_code")
        if sc != 20100:
            logger.warning(
                "DataForSEO search_volume task_post (location) status %s: %s (location=%s)",
                sc,
                tasks.get("status_message"),
                loc,
            )
            return None
        tid = tasks.get("id")
        return str(tid) if tid else None

    async def _fetch_maps_task_get_json(self, client: httpx.AsyncClient, task_id: str) -> dict | None:
        """GET task result; retry on transient HTTP/network errors (DataForSEO sometimes returns 5xx)."""
        url = f"{_BASE}/serp/google/maps/task_get/advanced/{task_id}"
        for http_try in range(_TASK_GET_HTTP_RETRIES):
            try:
                r = await client.get(url)
                if r.status_code in (500, 502, 503, 504, 429):
                    wait = min(32, 2**http_try)
                    logger.warning(
                        "DataForSEO task_get HTTP %s task=%s try %s/%s, sleeping %ss",
                        r.status_code,
                        task_id[:12],
                        http_try + 1,
                        _TASK_GET_HTTP_RETRIES,
                        wait,
                    )
                    await asyncio.sleep(wait)
                    continue
                r.raise_for_status()
                return r.json()
            except httpx.RequestError as exc:
                wait = min(32, 2**http_try)
                logger.warning(
                    "DataForSEO task_get network error task=%s: %s, sleeping %ss",
                    task_id[:12],
                    exc,
                    wait,
                )
                await asyncio.sleep(wait)
        logger.warning("DataForSEO task_get gave up after HTTP retries task=%s", task_id[:12])
        return None

    async def _poll_task(self, task_id: str) -> list[dict]:
        c = self._http()
        for attempt in range(_MAX_POLLS):
            data = await self._fetch_maps_task_get_json(c, task_id)
            if data is None:
                await asyncio.sleep(self._poll_sleep_s(attempt))
                continue
            tasks = (data.get("tasks") or [{}])[0]
            code = tasks.get("status_code")
            if code == 20000:
                res = tasks.get("result")
                items: list[dict] = []
                if isinstance(res, list) and len(res) > 0 and isinstance(res[0], dict):
                    items = res[0].get("items") or []
                elif isinstance(res, dict):
                    items = res.get("items") or []
                logger.info(
                    "DataForSEO maps task_get ready id=%s items=%d",
                    (task_id or "")[:16],
                    len(items),
                )
                return items
            # Queued / in progress — keep polling
            if code in (40601, 40602, 40600):
                await asyncio.sleep(self._poll_sleep_s(attempt))
                continue
            # 40102 = SERP returned no rows (often with strict pins); caller retries wider zoom.
            if code == 40102:
                logger.info(
                    "DataForSEO maps task_get: no SERP items (%s: %s), attempt %d",
                    code,
                    tasks.get("status_message"),
                    attempt,
                )
                return []
            logger.warning(
                "DataForSEO poll status %s: %s (attempt %d)",
                code, tasks.get("status_message"), attempt
            )
            return []
        return []

    async def _poll_search_volume_task(self, task_id: str) -> list[dict]:
        c = self._http()
        for attempt in range(_MAX_POLLS):
            r = await c.get(f"{_BASE}/keywords_data/google_ads/search_volume/task_get/{task_id}")
            r.raise_for_status()
            data = r.json()
            tasks = (data.get("tasks") or [{}])[0]
            code = tasks.get("status_code")
            if code == 20000:
                # task_get returns result rows directly (one row per keyword), not under result[0].items
                result = tasks.get("result") or []
                if isinstance(result, list):
                    return [x for x in result if isinstance(x, dict)]
                logger.warning("DataForSEO search_volume task_get unexpected shape: %s", type(result))
                return []
            if code in (40601, 40602, 40600):
                await asyncio.sleep(self._poll_sleep_s(attempt))
                continue
            logger.warning(
                "DataForSEO search_volume poll status %s: %s (attempt %d)",
                code, tasks.get("status_message"), attempt
            )
            return []
        return []

    async def _poll_keywords_for_keywords_task(self, task_id: str) -> list[dict]:
        c = self._http()
        for attempt in range(_MAX_POLLS):
            r = await c.get(
                f"{_BASE}/keywords_data/google_ads/keywords_for_keywords/task_get/{task_id}"
            )
            r.raise_for_status()
            data = r.json()
            tasks = (data.get("tasks") or [{}])[0]
            code = tasks.get("status_code")
            if code == 20000:
                result = tasks.get("result") or []
                if isinstance(result, list):
                    return [x for x in result if isinstance(x, dict)]
                logger.warning(
                    "DataForSEO keywords_for_keywords task_get unexpected shape: %s",
                    type(result),
                )
                return []
            if code in (40601, 40602, 40600):
                await asyncio.sleep(self._poll_sleep_s(attempt))
                continue
            logger.warning(
                "DataForSEO keywords_for_keywords poll status %s: %s (attempt %d)",
                code,
                tasks.get("status_message"),
                attempt,
            )
            return []
        return []

    def _previous_year_month(self) -> tuple[int, int]:
        now = datetime.now(UTC)
        yy = now.year
        mm = now.month - 1
        if mm == 0:
            yy -= 1
            mm = 12
        return yy, mm

    def _pick_exact_previous_month_volume(self, rows: list[dict]) -> int | None:
        """Volume for the calendar month before `now` (UTC), or None if that month is not in the payload."""
        yy, mm = self._previous_year_month()
        for r in rows:
            if not isinstance(r, dict):
                continue
            if int(r.get("year") or 0) == yy and int(r.get("month") or 0) == mm:
                try:
                    return int(r.get("search_volume"))
                except (TypeError, ValueError):
                    return None
        return None

    def _pick_latest_monthly_volume(self, rows: list[dict]) -> int | None:
        """Newest (year, month) row in `monthly_searches` — last resort when aggregate search_volume is absent."""
        valid: list[tuple[int, int, int]] = []
        for r in rows:
            if not isinstance(r, dict):
                continue
            try:
                valid.append((int(r.get("year")), int(r.get("month")), int(r.get("search_volume"))))
            except (TypeError, ValueError):
                continue
        if not valid:
            return None
        valid.sort(reverse=True)
        return valid[0][2]

    def _find_rank(self, items: list[dict], business_url: str, *, business_name: str | None = None) -> int | None:
        """rank_group / rank_absolute are 1-based in DataForSEO Maps responses."""
        target = _domain(business_url)
        brand_hint = (business_name or "").strip().lower() or _brand_hint_from_url(business_url)
        if not target:
            return None

        def _matches(raw: object) -> bool:
            if not raw or not isinstance(raw, str):
                return False
            raw_l = raw.lower()
            if target in raw_l:
                return True
            d = _domain(raw)
            return bool(d) and (d == target or d.endswith("." + target))

        pack_order = 0
        for item in items:
            pack_order += 1
            bits = (
                item.get("domain"),
                item.get("url"),
                item.get("contact_url"),
                item.get("original_url"),
            )
            domain_match = any(_matches(b) for b in bits)
            if not domain_match and brand_hint:
                title = str(item.get("title") or "").lower()
                title_match = brand_hint in title
                if not title_match:
                    continue
            elif not domain_match:
                continue
            return infer_maps_pack_rank(item, pack_order)
        return None

    async def google_business_updates_fetch_block(
        self,
        *,
        keyword: str,
        location_name: str,
        language_name: str = "English",
        depth: int = 20,
    ) -> dict | None:
        """POST Business Data Google Updates (GBP posts), poll, return ``result[0]`` or None."""
        kw = (keyword or "").strip()[:700]
        loc = (location_name or "").strip()
        if not kw or not loc:
            return None
        task: dict[str, object] = {
            "keyword": kw,
            "location_name": loc,
            "language_name": language_name,
            "depth": min(100, max(10, int(depth))),
        }
        c = self._http()
        r = await c.post(f"{_BASE}/business_data/google/my_business_updates/task_post", json=[task])
        r.raise_for_status()
        data = r.json()
        tasks = (data.get("tasks") or [{}])[0]
        if tasks.get("status_code") != 20100:
            logger.warning(
                "DataForSEO business updates task_post status %s: %s",
                tasks.get("status_code"),
                tasks.get("status_message"),
            )
            return None
        tid = tasks.get("id")
        if not tid:
            return None
        task_id = str(tid)

        url = f"{_BASE}/business_data/google/my_business_updates/task_get/{task_id}"
        for attempt in range(_MAX_REVIEWS_POLLS):
            payload = None
            for http_try in range(_TASK_GET_HTTP_RETRIES):
                try:
                    resp = await c.get(url)
                    if resp.status_code in (500, 502, 503, 504, 429):
                        await asyncio.sleep(min(32, 2**http_try))
                        continue
                    resp.raise_for_status()
                    payload = resp.json()
                    break
                except httpx.RequestError:
                    await asyncio.sleep(min(32, 2**http_try))
            if payload is None:
                await asyncio.sleep(self._poll_sleep_s(attempt))
                continue
            tsk = (payload.get("tasks") or [{}])[0]
            code = tsk.get("status_code")
            if code == 20000:
                res = tsk.get("result")
                if isinstance(res, list) and res and isinstance(res[0], dict):
                    return res[0]
                return None
            if code in (40601, 40602, 40600):
                await asyncio.sleep(self._poll_sleep_s(attempt))
                continue
            logger.warning(
                "DataForSEO business updates task_get status %s: %s",
                code,
                tsk.get("status_message"),
            )
            return None
        logger.warning("DataForSEO business updates timed out (task=%s)", task_id[:16])
        return None

    async def _fetch_google_reviews_task_get_json(self, client: httpx.AsyncClient, task_id: str) -> dict | None:
        url = f"{_BASE}/business_data/google/reviews/task_get/{task_id}"
        for http_try in range(_TASK_GET_HTTP_RETRIES):
            try:
                r = await client.get(url)
                if r.status_code in (500, 502, 503, 504, 429):
                    wait = min(32, 2**http_try)
                    await asyncio.sleep(wait)
                    continue
                r.raise_for_status()
                return r.json()
            except httpx.RequestError:
                wait = min(32, 2**http_try)
                await asyncio.sleep(wait)
        return None

    async def google_reviews_fetch_block(
        self,
        *,
        location_name: str,
        language_name: str = "English",
        depth: int = 30,
        sort_by: str = "newest",
        keyword: str | None = None,
        place_id: str | None = None,
    ) -> dict | None:
        """POST Business Data Google Reviews, poll task_get, return ``result[0]`` block or None."""
        loc = (location_name or "").strip()
        if not loc:
            return None
        task: dict[str, object] = {
            "location_name": loc,
            "language_name": language_name,
            "depth": min(100, max(10, int(depth))),
            "sort_by": sort_by,
        }
        pid = (place_id or "").strip()
        kw = (keyword or "").strip()[:700] if keyword else ""
        if pid and (pid.startswith("ChIJ") or pid.startswith("GhIJ")):
            task["place_id"] = pid
        elif kw:
            task["keyword"] = kw
        else:
            logger.warning("google_reviews_fetch_block: need keyword or place_id")
            return None

        c = self._http()
        r = await c.post(f"{_BASE}/business_data/google/reviews/task_post", json=[task])
        r.raise_for_status()
        data = r.json()
        tasks = (data.get("tasks") or [{}])[0]
        sc = tasks.get("status_code")
        if sc != 20100:
            logger.warning(
                "DataForSEO google reviews task_post status %s: %s",
                sc,
                tasks.get("status_message"),
            )
            return None
        tid = tasks.get("id")
        if not tid:
            return None
        task_id = str(tid)

        for attempt in range(_MAX_REVIEWS_POLLS):
            payload = await self._fetch_google_reviews_task_get_json(c, task_id)
            if payload is None:
                await asyncio.sleep(self._poll_sleep_s(attempt))
                continue
            tsk = (payload.get("tasks") or [{}])[0]
            code = tsk.get("status_code")
            if code == 20000:
                res = tsk.get("result")
                if isinstance(res, list) and res and isinstance(res[0], dict):
                    return res[0]
                if isinstance(res, dict):
                    return res
                return None
            if code in (40601, 40602, 40600):
                await asyncio.sleep(self._poll_sleep_s(attempt))
                continue
            logger.warning(
                "DataForSEO google reviews task_get status %s: %s",
                code,
                tsk.get("status_message"),
            )
            return None
        logger.warning(
            "DataForSEO google reviews task_get timed out after %d polls (task=%s)",
            _MAX_REVIEWS_POLLS,
            task_id[:16],
        )
        return None
