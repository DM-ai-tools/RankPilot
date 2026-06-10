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


async def ensure_rp_suburb_geo_table() -> None:
    """Matches infra/sql/015_suburb_geo.sql."""
    maker = session_maker()
    async with maker() as session:
        await session.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS rp_suburb_geo (
                  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                  suburb text NOT NULL,
                  state text,
                  postcode text,
                  lat double precision,
                  lng double precision,
                  geojson_polygon jsonb,
                  created_at timestamptz NOT NULL DEFAULT now(),
                  updated_at timestamptz NOT NULL DEFAULT now(),
                  UNIQUE (suburb, state, postcode)
                )
                """
            )
        )
        await session.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_rp_suburb_geo_lookup ON rp_suburb_geo (suburb, state, postcode)"
            )
        )
        await session.commit()
    logger.info("Schema check: rp_suburb_geo present")


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


async def ensure_rp_clients_location_scope() -> None:
    """Matches infra/sql/018_location_scope.sql."""
    maker = session_maker()
    async with maker() as session:
        await session.execute(
            text(
                """
                ALTER TABLE rp_clients
                ADD COLUMN IF NOT EXISTS location_scope text NOT NULL DEFAULT 'suburb',
                ADD COLUMN IF NOT EXISTS primary_suburb text NOT NULL DEFAULT ''
                """
            )
        )
        await session.commit()
    logger.info("Schema check: rp_clients.location_scope present")


async def ensure_rp_gbp_brand_kit_table() -> None:
    """Matches infra/sql/017_gbp_brand_kit.sql."""
    maker = session_maker()
    async with maker() as session:
        await session.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS rp_gbp_brand_kit (
                  client_id uuid PRIMARY KEY REFERENCES rp_clients(client_id) ON DELETE CASCADE,
                  brand_name text NOT NULL DEFAULT '',
                  agency_type text NOT NULL DEFAULT '',
                  language text NOT NULL DEFAULT 'English',
                  brand_voice text NOT NULL DEFAULT '',
                  forbidden_words text NOT NULL DEFAULT '',
                  primary_color text NOT NULL DEFAULT '#FF5F32',
                  secondary_color text NOT NULL DEFAULT '#000000',
                  heading_font text NOT NULL DEFAULT '',
                  body_font text NOT NULL DEFAULT '',
                  logo_on_dark_path text,
                  logo_on_light_path text,
                  updated_at timestamptz NOT NULL DEFAULT now()
                )
                """
            )
        )
        await session.commit()
    logger.info("Schema check: rp_gbp_brand_kit present")
