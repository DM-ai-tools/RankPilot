"""L4: Monthly reports — built from rank history, content, and citations."""

import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.deps import CurrentClientId, DbSession
from app.services.reports_service import generate_monthly_report_pdf, list_monthly_reports

router = APIRouter()

_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


@router.get("/monthly")
async def list_monthly_reports_route(client_id: CurrentClientId, session: DbSession) -> dict:
    items = await list_monthly_reports(session, client_id)
    return {"items": items}


@router.get("/monthly/{month}/pdf")
async def download_monthly_report_pdf(
    month: str,
    client_id: CurrentClientId,
    session: DbSession,
) -> Response:
    if not _MONTH_RE.match(month.strip()):
        raise HTTPException(status_code=400, detail="Month must be YYYY-MM (e.g. 2026-04)")
    try:
        pdf_bytes, filename = await generate_monthly_report_pdf(session, client_id, month.strip())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Failed to generate PDF") from exc

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
