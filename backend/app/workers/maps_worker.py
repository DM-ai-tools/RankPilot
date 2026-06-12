"""Maps-scan worker: DataForSEO for Google Maps pack ranks; Ahrefs for keyword volumes."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_ahrefs_api_key, get_settings
from app.db.session import session_maker
from app.data.au_suburbs import filter_suburbs_by_radius_km, filter_suburbs_from_center
from app.lib.maps_pack_rank import infer_maps_pack_rank
from app.services.ahrefs_cache_service import build_cache_key, build_suburbs_hash, get_ahrefs_cache, set_ahrefs_cache
from app.services.dataforseo_service import DataForSEOClient, format_maps_location_name
from app.services.keyword_lookup_service import _country_for_metro
from app.services.ranks_service import _ahrefs_volume_by_suburb

logger = logging.getLogger(__name__)

_BATCH = 10  # max parallel suburb tasks per scan job


def _serialize_maps_pack(items: list[dict], suburb: str, limit: int = 24) -> list[dict]:
    """Keep Maps SERP rows that include Google lat/lng (DataForSEO advanced Maps items)."""
    out: list[dict] = []
    pack_order = 0
    for it in items[:limit]:
        if not isinstance(it, dict):
            continue
        lat_raw, lng_raw = it.get("latitude"), it.get("longitude")
        try:
            la = float(lat_raw) if lat_raw is not None else None
            lo = float(lng_raw) if lng_raw is not None else None
        except (TypeError, ValueError):
            la = lo = None
        if la is None or lo is None:
            continue
        pack_order += 1
        rnk = infer_maps_pack_rank(it, pack_order)
        title = str(it.get("title") or "").strip() or "Business"
        dom = str(it.get("domain") or "").strip()[:160]
        url = str(it.get("url") or it.get("contact_url") or it.get("original_url") or "").strip()[:400]
        addr = str(it.get("address") or "").strip()[:240]
        # Persist review count + rating so competitor velocity can be derived without
        # extra API calls later.
        from app.lib.maps_pack_rank import maps_pack_rating_value, maps_pack_reviews_count

        reviews_count = maps_pack_reviews_count(it)
        rating_val = maps_pack_rating_value(it)
        out.append(
            {
                "title": title,
                "lat": la,
                "lng": lo,
                "rank": rnk,
                "domain": dom or None,
                "url": url or None,
                "address": addr or None,
                "suburb_context": suburb,
                "reviews_count": reviews_count,
                "rating": rating_val,
            }
        )
    return out


async def _load_ahrefs_volumes_for_scan(
    session: AsyncSession,
    *,
    client_id: str,
    keyword: str,
    suburb_names: list[str],
    metro: str,
) -> tuple[dict[str, int], str]:
    """Use 24h Ahrefs cache when available so scans skip a slow volume batch."""
    if not get_ahrefs_api_key() or not keyword or not suburb_names:
        return {}, "none"

    country = _country_for_metro(metro)
    vol_cache_key = build_cache_key(
        "ranks_volume",
        country,
        client_id,
        keyword,
        build_suburbs_hash(suburb_names),
    )
    cached_vols, _, _ = await get_ahrefs_cache(session, vol_cache_key)
    if isinstance(cached_vols, dict) and cached_vols.get("volumes"):
        volumes = {str(k): int(v) for k, v in cached_vols["volumes"].items()}
        return volumes, "ahrefs_cache"

    try:
        volumes = await _ahrefs_volume_by_suburb(keyword, suburb_names, metro=metro)
        await set_ahrefs_cache(
            session,
            vol_cache_key,
            {"volumes": volumes},
            client_id=UUID(client_id),
        )
        await session.commit()
        return volumes, "ahrefs"
    except Exception as exc:
        logger.warning("Ahrefs volume batch for maps_scan failed: %s", exc)
        return {}, "none"


async def _run_maps_scan(job_id: str, client_id: str, payload: dict) -> None:
    """Process one maps_scan job: rank each suburb, store history."""
    settings = get_settings()
    if not settings.dataforseo_login or not settings.dataforseo_password:
        logger.error("DataForSEO credentials missing — set DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD")
        await _update_job(job_id, "failed", error="DataForSEO credentials not set")
        return

    client = DataForSEOClient(settings)
    try:
        await _run_maps_scan_core(job_id, client_id, payload, client)
    finally:
        await client.aclose()


async def _run_maps_scan_core(job_id: str, client_id: str, payload: dict, client: DataForSEOClient) -> None:
    keyword = str(payload.get("keyword", "") or "").strip()
    if not keyword:
        await _update_job(job_id, "failed", error="No keyword in job payload")
        return

    maker = session_maker()

    # Mark running
    await _update_job(job_id, "running")

    async with maker() as session:
        # Disable RLS so we can read/write as the worker (service account)
        await session.execute(text("SET LOCAL row_security = off"))

        # Get client profile
        row = (
            await session.execute(
                text(
                    """
                    SELECT client_id, business_url, business_name, metro_label,
                           COALESCE(primary_suburb, '') AS primary_suburb,
                           COALESCE(search_radius_km, 25) AS search_radius_km
                    FROM rp_clients
                    WHERE client_id = :cid LIMIT 1
                    """
                ),
                {"cid": client_id},
            )
        ).mappings().first()
        if not row:
            await _update_job(job_id, "failed", error="Client not found")
            return

        business_url: str = str(row["business_url"] or "")
        metro: str = str(row["metro_label"] or "")
        if not business_url:
            await _update_job(job_id, "failed", error="No business_url on client — complete onboarding first")
            return

        # Load suburb grid
        suburbs_raw = (
            await session.execute(
                text(
                    """
                    SELECT id, suburb, state, postcode, lat, lng
                    FROM rp_suburb_grid
                    WHERE client_id = :cid
                    ORDER BY rank_priority ASC
                    """
                ),
                {"cid": client_id},
            )
        ).mappings().all()

        if not suburbs_raw:
            await _update_job(job_id, "failed", error="No suburbs in grid — complete onboarding first")
            return

        radius_km = max(
            5,
            min(100, int(payload.get("radius_km") or row.get("search_radius_km") or 25)),
        )
        suburbs_maps = [dict(s) for s in suburbs_raw]
        suburbs_before = len(suburbs_maps)
        anchor = str(row.get("primary_suburb") or "").strip()
        if anchor:
            centre = next(
                (s for s in suburbs_maps if str(s.get("suburb", "")).lower() == anchor.lower()),
                None,
            )
            if centre and centre.get("lat") is not None and centre.get("lng") is not None:
                suburbs_maps = filter_suburbs_from_center(
                    suburbs_maps,
                    float(centre["lat"]),
                    float(centre["lng"]),
                    radius_km,
                )
            else:
                suburbs_maps = filter_suburbs_by_radius_km(suburbs_maps, metro, radius_km)
        else:
            suburbs_maps = filter_suburbs_by_radius_km(suburbs_maps, metro, radius_km)
        suburbs = suburbs_maps

        logger.info(
            "maps_scan job %s: keyword=%s radius_km=%s suburbs_db=%d suburbs_to_scan=%d url=%s",
            job_id,
            keyword,
            radius_km,
            suburbs_before,
            len(suburbs),
            business_url,
        )

    # ---------- Ahrefs keyword volumes (cached when possible) ----------
    ahrefs_volumes: dict[str, int] = {}
    volume_source = "none"
    suburb_names = [str(s["suburb"]) for s in suburbs]
    async with maker() as session:
        await session.execute(text("SET LOCAL row_security = off"))
        ahrefs_volumes, volume_source = await _load_ahrefs_volumes_for_scan(
            session,
            client_id=client_id,
            keyword=keyword,
            suburb_names=suburb_names,
            metro=metro,
        )
    if volume_source == "ahrefs_cache":
        logger.info(
            "maps_scan job %s: Ahrefs volumes loaded from cache for %d suburbs",
            job_id,
            len(ahrefs_volumes),
        )
    elif volume_source == "ahrefs":
        logger.info(
            "maps_scan job %s: Ahrefs volumes fetched for %d suburbs",
            job_id,
            len(ahrefs_volumes),
        )
    elif not get_ahrefs_api_key():
        logger.info("maps_scan job %s: AHREFS_API_KEY not set — suburb volumes skipped", job_id)

    # ---------- parallel rank checks (batch of _BATCH at a time) ----------
    results: list[tuple[str, str, str, str, int | None, int | None, list[dict]]] = []
    checked_at = datetime.now(UTC)
    progress_lock = asyncio.Lock()
    progress = {"checked": 0, "total": len(suburbs), "found": 0, "inserted": 0}

    async def _check(
        suburb_id: str,
        suburb: str,
        state: str,
        postcode: str,
        lat: object | None,
        lng: object | None,
    ) -> None:
        lat_f = float(lat) if lat is not None else None
        lng_f = float(lng) if lng is not None else None
        location = format_maps_location_name(suburb, state)
        try:
            # Local query first; bare keyword only if suburb-specific search misses.
            candidates = [f"{keyword} {suburb}".strip(), keyword.strip()]
            seen: set[str] = set()
            uniq = [q for q in candidates if q and not (q.lower() in seen or seen.add(q.lower()))]
            rank = None
            serp_items: list[dict] = []
            for q in uniq:
                rank, serp_items = await client.get_maps_rank_with_serp(
                    keyword=q,
                    location=location,
                    business_url=business_url,
                    business_name=str(row.get("business_name") or ""),
                    lat=lat_f,
                    lng=lng_f,
                )
                if rank is not None or serp_items:
                    break
        except Exception as exc:
            logger.warning("Rank check failed for %s: %s", suburb, exc)
            rank = None
            serp_items = []
        vol = ahrefs_volumes.get(suburb) if volume_source == "ahrefs" else None
        pack = _serialize_maps_pack(serp_items, suburb)
        inserted = await _persist_suburb_rank(
            client_id,
            suburb_id,
            suburb,
            str(state or "").upper(),
            postcode,
            keyword,
            rank,
            vol,
            pack,
            checked_at,
            volume_source=volume_source,
        )
        results.append((suburb_id, suburb, str(state or "").upper(), postcode, rank, vol, pack))
        async with progress_lock:
            progress["checked"] += 1
            if rank is not None:
                progress["found"] += 1
            if inserted:
                progress["inserted"] += 1
            if progress["checked"] % 1 == 0 or progress["checked"] == progress["total"]:
                await _update_job_progress(
                    job_id,
                    result={
                        "progress": {
                            "suburbs_checked": progress["checked"],
                            "suburbs_total": progress["total"],
                            "found": progress["found"],
                            "rows_inserted": progress["inserted"],
                            "keyword": keyword,
                        }
                    },
                )
        logger.info("  %s → rank %s", suburb, rank)

    tasks = [
        _check(
            str(s["id"]),
            str(s["suburb"]),
            str(s["state"] or ""),
            str(s["postcode"] or ""),
            s.get("lat"),
            s.get("lng"),
        )
        for s in suburbs
    ]
    for i in range(0, len(tasks), _BATCH):
        batch = tasks[i : i + _BATCH]
        await asyncio.gather(*batch)

    await _reorder_suburb_priorities_by_volume(client_id, keyword)

    total = len(results)
    found = progress["found"]
    inserted = progress["inserted"]
    skipped_stale = total - inserted
    await _update_job(
        job_id,
        "succeeded",
        result={
            "suburbs_checked": total,
            "rows_inserted": inserted,
            "rows_skipped_stale": skipped_stale,
            "found": found,
            "keyword": keyword,
            "progress": {
                "suburbs_checked": total,
                "suburbs_total": total,
                "found": found,
                "rows_inserted": inserted,
                "keyword": keyword,
            },
        },
    )
    logger.info(
        "maps_scan %s done: %d/%d suburbs ranked, inserted=%d, skipped_stale=%d",
        job_id, found, total, inserted, skipped_stale,
    )


async def _update_job_progress(
    job_id: str,
    *,
    status: str | None = None,
    result: dict | None = None,
    error: str | None = None,
) -> None:
    import json  # noqa: PLC0415

    maker = session_maker()
    async with maker() as session:
        await session.execute(text("SET LOCAL row_security = off"))
        if status:
            await session.execute(
                text(
                    """
                    UPDATE rp_jobs
                    SET status = :status,
                        result = COALESCE((CAST(:res AS text))::jsonb, result),
                        error_message = COALESCE(:err, error_message),
                        updated_at = now()
                    WHERE id = :id
                    """
                ),
                {
                    "id": job_id,
                    "status": status,
                    "res": json.dumps(result) if result else None,
                    "err": error,
                },
            )
        else:
            await session.execute(
                text(
                    """
                    UPDATE rp_jobs
                    SET result = COALESCE(result, '{}'::jsonb) || (CAST(:res AS text))::jsonb,
                        updated_at = now()
                    WHERE id = :id
                    """
                ),
                {"id": job_id, "res": json.dumps(result or {})},
            )
        await session.commit()


async def _persist_suburb_rank(
    client_id: str,
    suburb_id: str,
    suburb: str,
    state: str,
    postcode: str,
    keyword: str,
    rank: int | None,
    vol: int | None,
    pack: list[dict],
    checked_at: datetime,
    *,
    volume_source: str = "none",
) -> bool:
    """Insert one rank_history row; return False if suburb row was stale."""
    import json  # noqa: PLC0415
    from uuid6 import uuid7  # noqa: PLC0415

    maker = session_maker()
    async with maker() as session:
        await session.execute(text("SET LOCAL row_security = off"))
        live_sid = (
            await session.execute(
                text(
                    """
                    SELECT id
                    FROM rp_suburb_grid
                    WHERE client_id = :cid
                      AND suburb = :suburb
                      AND state = :state
                      AND postcode = :postcode
                    LIMIT 1
                    """
                ),
                {"cid": client_id, "suburb": suburb, "state": state, "postcode": postcode},
            )
        ).scalar_one_or_none()
        if live_sid is None:
            return False

        await session.execute(
            text(
                """
                INSERT INTO rp_rank_history
                    (id, client_id, suburb_id, keyword, rank_position, feature_snapshot, checked_at)
                VALUES
                    (:id, :cid, :sid, :kw, :rank, (CAST(:snap AS text))::jsonb, :ts)
                """
            ),
            {
                "id": str(uuid7()),
                "cid": client_id,
                "sid": str(live_sid),
                "kw": keyword,
                "rank": rank,
                "snap": json.dumps(
                    {
                        "state": state,
                        "monthly_search_volume": vol,
                        "volume_source": volume_source,
                        "maps_pack": pack,
                    }
                ),
                "ts": checked_at,
            },
        )
        await session.commit()
        return True


async def _reorder_suburb_priorities_by_volume(client_id: str, keyword: str) -> None:
    """Set rank_priority on rp_suburb_grid by latest keyword search volume (highest first)."""
    maker = session_maker()
    async with maker() as session:
        await session.execute(text("SET LOCAL row_security = off"))
        rows = (
            await session.execute(
                text(
                    """
                    SELECT DISTINCT ON (s.id)
                      s.id,
                      COALESCE(
                        NULLIF((r.feature_snapshot->>'monthly_search_volume')::int, 0),
                        GREATEST(1, COALESCE(s.population, 0) * 14 / 1000)
                      ) AS vol
                    FROM rp_suburb_grid s
                    LEFT JOIN rp_rank_history r
                      ON r.suburb_id = s.id
                     AND r.client_id = s.client_id
                     AND LOWER(TRIM(r.keyword)) = LOWER(TRIM(:kw))
                    WHERE s.client_id = :cid
                    ORDER BY s.id, r.checked_at DESC NULLS LAST
                    """
                ),
                {"cid": client_id, "kw": keyword},
            )
        ).mappings().all()
        ordered = sorted(rows, key=lambda r: int(r.get("vol") or 0), reverse=True)
        for pri, row in enumerate(ordered, start=1):
            await session.execute(
                text(
                    """
                    UPDATE rp_suburb_grid
                    SET rank_priority = :pri, updated_at = now()
                    WHERE id = :id AND client_id = :cid
                    """
                ),
                {"pri": pri, "id": str(row["id"]), "cid": client_id},
            )
        await session.commit()


async def _update_job(
    job_id: str,
    status: str,
    *,
    error: str | None = None,
    result: dict | None = None,
) -> None:
    import json  # noqa: PLC0415

    maker = session_maker()
    async with maker() as session:
        await session.execute(text("SET LOCAL row_security = off"))
        await session.execute(
            text(
                """
                UPDATE rp_jobs
                SET status = :status,
                    error_message = :err,
                    result = (CAST(:res AS text))::jsonb,
                    updated_at = now()
                WHERE id = :id
                """
            ),
            {
                "id": job_id,
                "status": status,
                "err": error,
                "res": json.dumps(result) if result else None,
            },
        )
        await session.commit()


async def _run_maps_scan_safe(job_id: str, client_id: str, payload: dict) -> None:
    """Wrapper so worker crashes don't leave jobs stuck in 'running'."""
    try:
        await _run_maps_scan(job_id, client_id, payload)
    except Exception as exc:  # pragma: no cover - defensive worker guard
        logger.exception("maps_scan %s crashed: %s", job_id, exc)
        await _update_job(job_id, "failed", error=str(exc))


def _exception_walk(exc: BaseException) -> list[BaseException]:
    """SQLAlchemy/asyncpg often wrap Errno 111 under OperationalError — walk causes and .orig."""
    out: list[BaseException] = []
    seen: set[int] = set()
    stack: list[BaseException] = [exc]
    while stack:
        cur = stack.pop()
        if cur is None or id(cur) in seen:
            continue
        seen.add(id(cur))
        out.append(cur)
        stack.append(cur.__cause__)  # type: ignore[arg-type]
        ctx = getattr(cur, "__context__", None)
        if isinstance(ctx, BaseException):
            stack.append(ctx)
        orig = getattr(cur, "orig", None)
        if isinstance(orig, BaseException):
            stack.append(orig)
    return out


def _is_transient_db_connect_error(exc: BaseException) -> bool:
    """True for TCP refused / timeouts so we log briefly instead of full traceback every poll."""
    if isinstance(exc, OperationalError):
        low = str(exc).lower()
        if any(
            x in low
            for x in (
                "connection refused",
                "could not connect",
                "timeout",
                "name or service not known",
                "errno 111",
            )
        ):
            return True
    for cur in _exception_walk(exc):
        if isinstance(cur, (ConnectionRefusedError, TimeoutError, asyncio.TimeoutError)):
            return True
        if isinstance(cur, OSError) and getattr(cur, "errno", None) in (111, 110):
            return True
        msg = str(cur).lower()
        if "connection refused" in msg or "cannot connect" in msg or "name or service not known" in msg:
            return True
    return False


_last_db_poll_warn_mono: float = 0.0
_DB_POLL_WARN_INTERVAL_SEC = 300.0


async def poll_and_run_jobs() -> None:
    """Dequeue one pending maps_scan job and run it. Called by scheduler."""
    global _last_db_poll_warn_mono
    try:
        maker = session_maker()
        async with maker() as session:
            await session.execute(text("SET LOCAL row_security = off"))
            row = (
                await session.execute(
                    text(
                        """
                        SELECT id, client_id, payload
                        FROM rp_jobs
                        WHERE job_type = 'maps_scan'
                          AND status = 'queued'
                        ORDER BY created_at ASC
                        LIMIT 1
                        FOR UPDATE SKIP LOCKED
                        """
                    )
                )
            ).mappings().first()
            if not row:
                return
            job_id = str(row["id"])
            client_id = str(row["client_id"])
            payload = row["payload"] if isinstance(row["payload"], dict) else {}
            # Immediately claim
            await session.execute(
                text("UPDATE rp_jobs SET status='running', updated_at=now() WHERE id=:id"),
                {"id": job_id},
            )
            await session.commit()

        asyncio.create_task(_run_maps_scan_safe(job_id, client_id, payload))
    except Exception as exc:
        if _is_transient_db_connect_error(exc):
            now = time.monotonic()
            if now - _last_db_poll_warn_mono >= _DB_POLL_WARN_INTERVAL_SEC:
                _last_db_poll_warn_mono = now
                logger.error(
                    "poll_and_run_jobs: database unreachable (%s). Fix DATABASE_URL / Postgres service; "
                    "suppressing repeated tracebacks for %s s.",
                    exc,
                    int(_DB_POLL_WARN_INTERVAL_SEC),
                )
            return
        logger.exception("poll_and_run_jobs error")
