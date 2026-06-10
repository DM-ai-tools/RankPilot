"""Print recent maps_scan jobs."""
from __future__ import annotations

import asyncio
import json

from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import configure_engine, session_maker


async def main() -> None:
    configure_engine(get_settings().database_url)
    maker = session_maker()
    async with maker() as session:
        await session.execute(text("SET LOCAL row_security = off"))
        rows = (
            await session.execute(
                text(
                    """
                    SELECT id, status, payload, result, error_message,
                           created_at, updated_at
                    FROM rp_jobs
                    WHERE job_type = 'maps_scan'
                    ORDER BY created_at DESC
                    LIMIT 5
                    """
                )
            )
        ).mappings().all()
        for r in rows:
            print("---")
            print("id:", r["id"])
            print("status:", r["status"])
            print("payload:", r["payload"])
            prog = (r["result"] or {}).get("progress") if r["result"] else None
            if prog:
                print("progress:", prog)
            if r["error_message"]:
                print("error:", r["error_message"])
            print("created:", r["created_at"])
            print("updated:", r["updated_at"])

        cnt = (
            await session.execute(
                text(
                    """
                    SELECT COUNT(*) AS n
                    FROM rp_suburb_grid
                    WHERE client_id = (
                        SELECT client_id FROM rp_jobs
                        WHERE job_type = 'maps_scan'
                        ORDER BY created_at DESC LIMIT 1
                    )
                    """
                )
            )
        ).scalar_one()
        print("\nsuburbs in grid for latest scan client:", cnt)


if __name__ == "__main__":
    asyncio.run(main())
