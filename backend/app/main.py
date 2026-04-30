"""L4: API gateway — mounts versioned REST routes under /api/v1."""

import asyncio
import logging
import os
import subprocess
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.db.schema_bootstrap import (
    ensure_rp_clients_nap_columns,
    ensure_rp_clients_search_radius,
    ensure_rp_suburb_grid_client_index,
)
from sqlalchemy import text
from sqlalchemy.engine.url import make_url

from app.db.session import configure_engine, dispose_engine, session_maker
from app.routes.v1 import api_router
from app.workers.maps_worker import poll_and_run_jobs
from app.workers.scheduler import register_jobs, scheduler

logger = logging.getLogger(__name__)


def _redact_database_url(raw: str) -> str:
    """Log-friendly DATABASE_URL (password hidden)."""
    try:
        u = make_url(raw)
        return u.render_as_string(hide_password=True)
    except Exception:
        return "<invalid DATABASE_URL>"


def _warn_railway_localhost_db(database_url: str) -> None:
    if not os.environ.get("RAILWAY_ENVIRONMENT") and not os.environ.get("RAILWAY_PROJECT_ID"):
        return
    low = (database_url or "").lower()
    if "localhost" in low or "127.0.0.1" in low:
        logger.critical(
            "DATABASE_URL points at localhost but this process runs on Railway. "
            "Add the Postgres plugin to the project and set DATABASE_URL via Variable Reference "
            "to that service (hostname is never localhost inside the container)."
        )


async def _ping_database() -> None:
    """Fail fast if Postgres is unreachable (do not treat as 'missing tables')."""
    async with session_maker()() as s:
        await s.execute(text("SELECT 1"))


async def _core_schema_ready() -> bool:
    """True once infra/sql migrations have been applied (rp_jobs exists). DB must already respond."""
    async with session_maker()() as s:
        r = await s.execute(text("SELECT to_regclass('public.rp_jobs')"))
        return r.scalar() is not None


def _apply_migrations_subprocess() -> int:
    """Run infra/sql via psql (same as `python scripts/apply_migrations.py`). Returns exit code."""
    root = Path(__file__).resolve().parent.parent
    script = root / "scripts" / "apply_migrations.py"
    if not script.is_file():
        logger.error("Migration script missing: %s", script)
        return 1
    return subprocess.run(
        [sys.executable, str(script)],
        cwd=str(root),
        env=os.environ.copy(),
        check=False,
    ).returncode


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
    _warn_railway_localhost_db(settings.database_url)
    logger.info("PostgreSQL target: %s", _redact_database_url(settings.database_url))

    try:
        await _ping_database()
    except Exception as exc:
        logger.critical(
            "Cannot reach PostgreSQL at startup (%s). The public API URL can still work for routes "
            "that do not touch the DB, but /api/v1 and workers need a valid DATABASE_URL. "
            "On Railway: Variables → add reference to your Postgres service; redeploy.",
            exc,
        )
        raise

    schema_ok = await _core_schema_ready()
    if not schema_ok and not settings.skip_auto_sql_migrate:
        logger.warning(
            "RankPilot core tables missing; applying infra/sql migrations automatically "
            "(Railway and other hosts without an interactive shell)."
        )
        code = await asyncio.to_thread(_apply_migrations_subprocess)
        schema_ok = await _core_schema_ready()
        if code != 0 and not schema_ok:
            logger.critical(
                "apply_migrations.py exited with %s; DATABASE_URL must reach Postgres and "
                "infra/sql must apply cleanly. Check deploy logs above.",
                code,
            )
            raise RuntimeError("RankPilot: database migration failed")
        if code != 0 and schema_ok:
            logger.info(
                "apply_migrations.py exited with %s but schema is present (likely concurrent deploy); continuing.",
                code,
            )
        elif schema_ok:
            logger.info("Database migrations applied; core tables present.")

    if schema_ok:
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

    if not schema_ok:
        logger.error(
            "PostgreSQL is reachable but RankPilot tables are still missing. "
            "If you disabled auto-migrate, unset RANKPILOT_SKIP_AUTO_MIGRATE or run locally: "
            "cd backend && python scripts/apply_migrations.py (with DATABASE_URL pointing at this DB). "
            "Scheduler stays off until tables exist."
        )
    else:
        # Reset any jobs left in 'running' from a previous hot-reload / crash.
        try:
            async with session_maker()() as _s:
                await _s.execute(text("SET LOCAL row_security = off"))
                res = await _s.execute(
                    text("UPDATE rp_jobs SET status='queued', updated_at=now() WHERE status='running'")
                )
                await _s.commit()
                if res.rowcount:
                    logger.warning(
                        "Recovered %d interrupted maps_scan job(s) (status reset to queued)", res.rowcount
                    )
        except Exception:
            logger.exception("Job recovery step failed (non-fatal)")

        register_jobs()
        scheduler.start()
        try:
            await poll_and_run_jobs()
        except Exception:
            logger.exception("Initial maps_scan job poll failed (scheduler will retry)")
    yield
    try:
        scheduler.shutdown(wait=False)
    except Exception:
        pass
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
    @app.get("/", tags=["health"])
    async def root() -> dict[str, str]:
        """Public URL often hits `/` in browsers — API lives under /api/v1 and /docs."""
        return {
            "service": settings.app_name,
            "health": "/health",
            "openapi": "/openapi.json",
            "docs": "/docs",
            "api": settings.api_v1_prefix,
            "hint": "404 on / alone was normal before this route; use /docs or /api/v1 for the app.",
        }

    @app.get("/health", tags=["health"])
    async def health_root() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
