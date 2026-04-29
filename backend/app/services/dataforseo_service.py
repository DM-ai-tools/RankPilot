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

logger = logging.getLogger(__name__)

_BASE = "https://api.dataforseo.com/v3"
# Polling: short sleeps early (tasks often finish within ~15s), then back off.
_POLL_FAST_S = 3
_POLL_INTERVAL_S = 7
_POLL_FAST_ATTEMPTS = 6
_MAX_POLLS = 18  # ~2 min worst-case per task
_TASK_GET_HTTP_RETRIES = 5  # retry transient 5xx / network on task_get

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
                limits=httpx.Limits(max_connections=32, max_keepalive_connections=16),
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
            (11, None),
            (9, False),
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
        task = {
            "keywords": [keyword],
            "location_name": _state_location_name(state_abbr),
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
                "DataForSEO search_volume task_post status %s: %s",
                sc,
                tasks.get("status_message"),
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

        for item in items:
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
            pos = item.get("rank_group")
            if pos is None:
                pos = item.get("rank_absolute")
            if pos is None:
                continue
            try:
                return int(pos)
            except (TypeError, ValueError):
                continue
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

        for attempt in range(_MAX_POLLS):
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
        return None
