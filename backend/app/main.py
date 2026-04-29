"""L4: API gateway — mounts versioned REST routes under /api/v1."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.db.schema_bootstrap import (
    ensure_rp_clients_nap_columns,
    ensure_rp_clients_search_radius,
    ensure_rp_suburb_grid_client_index,
)
from app.db.session import configure_engine, dispose_engine
from app.routes.v1 import api_router
from app.workers.maps_worker import poll_and_run_jobs
from app.workers.scheduler import register_jobs, scheduler

logger = logging.getLogger(__name__)


def _cors_allow_origins(settings) -> list[str]:
    raw = (settings.cors_origins or "").strip()
    parts = [x.strip() for x in raw.split(",") if x.strip()]
    return parts or ["http://localhost:5173"]


def _cors_allow_origin_regex(settings) -> str | None:
    """Allow all Railway-generated subdomains automatically."""
    raw = (settings.cors_origins or "").strip()
    # If operator set an explicit list, no regex needed.
    if raw and "railway.app" not in raw:
        return None
    return r"https://.*\.railway\.app"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    configure_engine(settings.database_url, echo=settings.debug)
    try:
        await ensure_rp_clients_search_radius()
    except Exception:
        logger.exception("Schema bootstrap: search_radius_km (see infra/sql/009_search_radius.sql)")
    try:
        await ensure_rp_clients_nap_columns()
    except Exception:
        logger.exception("Schema bootstrap: business NAP columns (see infra/sql/011_business_nap.sql)")
    try:
        await ensure_rp_suburb_grid_client_index()
    except Exception:
        logger.exception("Schema bootstrap: suburb grid index (see infra/sql/010_perf_indexes.sql)")

    s = get_settings()
    if str(s.dataforseo_login or "").strip() and str(s.dataforseo_password or "").strip():
        logger.info("DataForSEO credentials loaded (maps_scan + keyword volume enabled).")
    else:
        logger.warning(
            "DataForSEO credentials missing — set DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD in backend/.env "
            "(aliases: DATAFORSEO_API_LOGIN / DATAFORSEO_API_PASSWORD)."
        )

    # Reset any jobs left in 'running' from a previous hot-reload / crash.
    # Without this, uvicorn --reload restarts leave jobs stuck forever.
    try:
        from app.db.session import session_maker
        from sqlalchemy import text as _text
        async with session_maker()() as _s:
            await _s.execute(_text("SET LOCAL row_security = off"))
            res = await _s.execute(
                _text("UPDATE rp_jobs SET status='queued', updated_at=now() WHERE status='running'")
            )
            await _s.commit()
            if res.rowcount:
                logger.warning("Recovered %d interrupted maps_scan job(s) (status reset to queued)", res.rowcount)
    except Exception:
        logger.exception("Job recovery step failed (non-fatal)")

    register_jobs()
    scheduler.start()
    try:
        await poll_and_run_jobs()
    except Exception:
        logger.exception("Initial maps_scan job poll failed (scheduler will retry)")
    yield
    scheduler.shutdown(wait=False)
    await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, lifespan=lifespan, version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_allow_origins(settings),
        allow_origin_regex=_cors_allow_origin_regex(settings),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    @app.get("/health", tags=["health"])
    async def health_root() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
