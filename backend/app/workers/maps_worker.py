"""Maps-scan worker: picks up rp_jobs rows, calls DataForSEO, writes rp_rank_history."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import session_maker
from app.data.au_suburbs import filter_suburbs_by_radius_km
from app.services.dataforseo_service import DataForSEOClient, format_maps_location_name

logger = logging.getLogger(__name__)

_BATCH = 5  # max parallel suburb tasks per scan job


def _serialize_maps_pack(items: list[dict], suburb: str, limit: int = 24) -> list[dict]:
    """Keep Maps SERP rows that include Google lat/lng (DataForSEO advanced Maps items)."""
    out: list[dict] = []
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
        rg = it.get("rank_group")
        if rg is None:
            rg = it.get("rank_absolute")
        try:
            rnk = int(rg) if rg is not None else None
        except (TypeError, ValueError):
            rnk = None
        title = str(it.get("title") or "").strip() or "Business"
        dom = str(it.get("domain") or "").strip()[:160]
        url = str(it.get("url") or it.get("contact_url") or it.get("original_url") or "").strip()[:400]
        addr = str(it.get("address") or "").strip()[:240]
        # Persist review count + rating so competitor velocity can be derived without
        # extra API calls later.
        rc_raw = it.get("reviews_count") or it.get("rating", {})
        try:
            reviews_count = int(it.get("reviews_count")) if it.get("reviews_count") is not None else None
        except (TypeError, ValueError):
            reviews_count = None
        rating_raw = it.get("rating")
        try:
            rating_val = float(rating_raw.get("value")) if isinstance(rating_raw, dict) else (float(rating_raw) if rating_raw is not None else None)
        except (TypeError, ValueError, AttributeError):
            rating_val = None
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
                    SELECT client_id, business_url, business_name, metro_label
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

        radius_km = max(5, min(100, int(payload.get("radius_km") or 25)))
        suburbs_maps = [dict(s) for s in suburbs_raw]
        suburbs_before = len(suburbs_maps)
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

    # ---------- state-wise keyword volume (previous month) ----------
    state_volume: dict[str, int | None] = {}
    for s in {str(x["state"] or "").upper() for x in suburbs}:
        if not s:
            continue
        try:
            vol = await client.get_state_keyword_volume(keyword=keyword, state_abbr=s)
        except Exception as exc:
            logger.warning("Search volume fetch failed for %s: %s", s, exc)
            vol = None
        state_volume[s] = vol

    # ---------- parallel rank checks (batch of _BATCH at a time) ----------
    results: list[tuple[str, str, str, str, int | None, int | None, list[dict]]] = []

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
            candidates: list[str] = [
                keyword,
                f"{keyword} {suburb}",
                f"{keyword} {suburb} {state}",
                f"{keyword} near {suburb}",
            ]
            words = [w for w in str(keyword or "").split() if w]
            if len(words) >= 3:
                candidates.append(" ".join(words[:3]))
            if len(words) >= 2:
                candidates.append(" ".join(words[:2]))
            # Deduplicate while preserving order.
            seen: set[str] = set()
            uniq = [q for q in candidates if not (q in seen or seen.add(q))]
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
                if rank is not None:
                    break
        except Exception as exc:
            logger.warning("Rank check failed for %s: %s", suburb, exc)
            rank = None
            serp_items = []
        vol = state_volume.get(str(state or "").upper())
        pack = _serialize_maps_pack(serp_items, suburb)
        results.append((suburb_id, suburb, str(state or "").upper(), postcode, rank, vol, pack))
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

    # ---------- write rank history ----------
    now = datetime.now(UTC)
    from uuid6 import uuid7  # noqa: PLC0415

    async with maker() as session:
        await session.execute(text("SET LOCAL row_security = off"))
        import json  # noqa: PLC0415

        inserted = 0
        skipped_stale = 0
        for suburb_id, suburb, state, postcode, rank, vol, pack in results:
            # Onboarding can reseed suburb grid while a scan is running, which changes suburb IDs.
            # Resolve the current suburb ID by natural key to avoid FK failures and keep the job alive.
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
                    {
                        "cid": client_id,
                        "suburb": suburb,
                        "state": state,
                        "postcode": postcode,
                    },
                )
            ).scalar_one_or_none()
            if live_sid is None:
                skipped_stale += 1
                continue

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
                            "volume_source": "dataforseo_keywords_data_google_ads",
                            "maps_pack": pack,
                        }
                    ),
                    "ts": now,
                },
            )
            inserted += 1
        await session.commit()

    total = len(results)
    found = sum(1 for _, _, _, _, r, _, _ in results if r is not None)
    await _update_job(
        job_id,
        "succeeded",
        result={
            "suburbs_checked": total,
            "rows_inserted": inserted,
            "rows_skipped_stale": skipped_stale,
            "found": found,
            "keyword": keyword,
        },
    )
    logger.info(
        "maps_scan %s done: %d/%d suburbs ranked, inserted=%d, skipped_stale=%d",
        job_id, found, total, inserted, skipped_stale,
    )


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
