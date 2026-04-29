import logging

from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import session_maker
from app.schemas.health import HealthResponse, ReadyResponse

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/ping", response_model=HealthResponse)
async def ping() -> HealthResponse:
    return HealthResponse()


@router.get("/ready", response_model=ReadyResponse)
async def ready() -> ReadyResponse:
    """DB + DataForSEO env presence. Call after deploy to verify credentials load."""
    settings = get_settings()
    df = bool(str(settings.dataforseo_login or "").strip() and str(settings.dataforseo_password or "").strip())
    db_ok = False
    try:
        maker = session_maker()
        async with maker() as session:
            await session.execute(text("SELECT 1"))
            db_ok = True
    except Exception as exc:
        logger.warning("ready check DB failed: %s", exc)
    return ReadyResponse(
        ok=db_ok and df,
        database_reachable=db_ok,
        dataforseo_credentials_present=df,
    )
