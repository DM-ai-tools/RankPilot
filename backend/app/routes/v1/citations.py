"""L4: Citations — rp_citations."""

import json

from fastapi import APIRouter
from sqlalchemy import text

from app.deps import CurrentClientId, DbSession
from app.schemas.citations_public import CitationRow, CitationsListResponse, ScrapedNap
from app.services.citations_sync_service import sync_citations_for_client

router = APIRouter()


@router.get("/directories", response_model=CitationsListResponse)
async def citation_directory_status(session: DbSession) -> CitationsListResponse:
    rows = (
        await session.execute(
            text(
                """
                SELECT id, directory, status, drift_flag, last_checked, scraped_nap
                FROM rp_citations
                ORDER BY
                  CASE status
                    WHEN 'missing'      THEN 1
                    WHEN 'inconsistent' THEN 2
                    WHEN 'fixing'       THEN 3
                    WHEN 'queued'       THEN 4
                    ELSE 5
                  END,
                  directory ASC
                """
            )
        )
    ).mappings().all()

    items: list[CitationRow] = []
    for r in rows:
        raw = r["scraped_nap"]
        scraped: ScrapedNap | None = None
        if raw:
            try:
                d = json.loads(raw) if isinstance(raw, str) else raw
                scraped = ScrapedNap(**d)
            except Exception:
                scraped = None
        items.append(
            CitationRow(
                id=r["id"],
                directory=str(r["directory"]),
                status=str(r["status"]),
                drift_flag=bool(r["drift_flag"]),
                last_checked=r["last_checked"],
                scraped_nap=scraped,
            )
        )
    return CitationsListResponse(items=items)


@router.post("/sync")
async def sync_citations(
    client_id: CurrentClientId,
    session: DbSession,
) -> dict:
    """Run Firecrawl citation checks and upsert rp_citations for the current tenant."""
    return await sync_citations_for_client(session, client_id)
