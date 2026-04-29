from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "rankpilot-api"


class ReadyResponse(BaseModel):
    """Runtime checks for operators (no secrets returned)."""

    ok: bool
    database_reachable: bool
    dataforseo_credentials_present: bool
    maps_worker_scheduler: bool = True
