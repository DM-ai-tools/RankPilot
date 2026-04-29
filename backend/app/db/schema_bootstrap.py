"""Idempotent DDL for dev/small installs when infra/sql migrations were not applied manually."""

from __future__ import annotations

import logging

from sqlalchemy import text

from app.db.session import session_maker

logger = logging.getLogger(__name__)


async def ensure_rp_clients_search_radius() -> None:
    """Add search_radius_km if missing (matches infra/sql/009_search_radius.sql)."""
    maker = session_maker()
    async with maker() as session:
        await session.execute(
            text(
                """
                ALTER TABLE rp_clients
                ADD COLUMN IF NOT EXISTS search_radius_km integer NOT NULL DEFAULT 25
                """
            )
        )
        await session.commit()
    logger.info("Schema check: rp_clients.search_radius_km present")


async def ensure_rp_suburb_grid_client_index() -> None:
    """Matches infra/sql/010_perf_indexes.sql — helps dashboard queries under RLS."""
    maker = session_maker()
    async with maker() as session:
        await session.execute(
            text("CREATE INDEX IF NOT EXISTS idx_rp_suburb_grid_client_id ON rp_suburb_grid (client_id)")
        )
        await session.commit()
    logger.info("Schema check: idx_rp_suburb_grid_client_id present")


async def ensure_rp_clients_nap_columns() -> None:
    """Add business_address/business_phone if missing (infra/sql/011_business_nap.sql)."""
    maker = session_maker()
    async with maker() as session:
        await session.execute(
            text(
                """
                ALTER TABLE rp_clients
                ADD COLUMN IF NOT EXISTS business_address text NOT NULL DEFAULT '',
                ADD COLUMN IF NOT EXISTS business_phone text NOT NULL DEFAULT ''
                """
            )
        )
        await session.commit()
    logger.info("Schema check: rp_clients business_address/business_phone present")
