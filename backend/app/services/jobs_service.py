"""Background job records (L1 workers update status)."""

import json
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.common import JobAcceptedResponse
from app.schemas.jobs import JobStatusResponse, ScanCreateRequest


class JobsService:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_job(self, client_id: UUID, job_id: UUID) -> JobStatusResponse | None:
        row = (
            await self._session.execute(
                text(
                    """
                    SELECT id, job_type, status, payload, result, error_message, created_at, updated_at
                    FROM rp_jobs
                    WHERE id = :jid AND client_id = :cid
                    """
                ),
                {"jid": str(job_id), "cid": str(client_id)},
            )
        ).mappings().first()
        if not row:
            return None
        return JobStatusResponse(
            job_id=row["id"],
            job_type=str(row["job_type"]),
            status=str(row["status"]),
            payload=dict(row["payload"] or {}),
            result=dict(row["result"]) if row["result"] else None,
            error_message=row["error_message"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    async def enqueue_scan(self, client_id: UUID, body: ScanCreateRequest) -> JobAcceptedResponse:
        from uuid6 import uuid7

        kw = (body.keyword or "").strip()
        if not kw:
            row = (
                await self._session.execute(
                    text("SELECT primary_keyword FROM rp_clients WHERE client_id = :cid"),
                    {"cid": str(client_id)},
                )
            ).mappings().first()
            kw = str(row["primary_keyword"] if row else "").strip()
        if not kw:
            raise ValueError(
                "Set a primary service keyword (onboarding or dashboard) before running a Maps scan."
            )

        # Dashboard / Keywords / overview all join rp_rank_history on rp_clients.primary_keyword.
        # Keep them aligned whenever a scan is queued (explicit keyword or resolved from profile).
        await self._session.execute(
            text(
                """
                UPDATE rp_clients
                SET primary_keyword = :kw, updated_at = now()
                WHERE client_id = :cid
                """
            ),
            {"kw": kw, "cid": str(client_id)},
        )

        jid = uuid7()
        if body.radius_km is not None:
            radius = max(5, min(100, int(body.radius_km)))
        else:
            crow = (
                await self._session.execute(
                    text(
                        "SELECT COALESCE(search_radius_km, 25) AS r FROM rp_clients WHERE client_id = :cid"
                    ),
                    {"cid": str(client_id)},
                )
            ).mappings().first()
            radius = int(crow["r"]) if crow else 25
        payload = {"keyword": kw, "radius_km": radius}
        # One idempotency key per job so every "Save & scan" / "Re-run" queues a new worker run
        # (old ON CONFLICT same keyword+radius silently skipped re-scans).
        idem = str(jid)
        await self._session.execute(
            text(
                """
                INSERT INTO rp_jobs (id, client_id, job_type, status, payload, idempotency_key)
                VALUES (:id, :cid, 'maps_scan', 'queued', (CAST(:payload AS text))::jsonb, :idem)
                """
            ),
            {
                "id": str(jid),
                "cid": str(client_id),
                "payload": json.dumps(payload),
                "idem": idem,
            },
        )
        return JobAcceptedResponse(job_id=jid, status="queued")
