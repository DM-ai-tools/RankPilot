"""FastAPI dependencies — JWT client context, service injection."""

from collections.abc import AsyncGenerator
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import session_maker

security = HTTPBearer(auto_error=False)


async def get_current_client_id(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> UUID:
    """Resolve tenant from JWT `sub` or `client_id` claim. Stub: replace with real auth."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        raw = payload.get("client_id") or payload.get("sub")
        if raw is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token claims")
        return UUID(str(raw))
    except (JWTError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        ) from None


CurrentClientId = Annotated[UUID, Depends(get_current_client_id)]


async def get_db(client_id: CurrentClientId) -> AsyncGenerator[AsyncSession, None]:
    """Tenant-scoped DB session (sets `app.client_id` for RLS)."""
    from sqlalchemy import text

    maker = session_maker()
    async with maker() as session:
        await session.execute(
            text("SELECT set_config('app.client_id', :cid, true)"),
            {"cid": str(client_id)},
        )
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


DbSession = Annotated[AsyncSession, Depends(get_db)]


async def get_login_db() -> AsyncGenerator[AsyncSession, None]:
    """
    One-off session for unauthenticated login only.
    Disables RLS briefly so `rp_clients` can be read by email before `app.client_id` exists.
    """
    from sqlalchemy import text

    maker = session_maker()
    async with maker() as session:
        await session.execute(text("SET LOCAL row_security = off"))
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


LoginDbSession = Annotated[AsyncSession, Depends(get_login_db)]


async def get_oauth_callback_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Session for OAuth callback endpoints.
    Callback is unauthenticated by design; tenant is resolved from signed `state`,
    then set via `set_config('app.client_id', ...)` inside the route handler.
    """
    maker = session_maker()
    async with maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


OAuthCallbackDbSession = Annotated[AsyncSession, Depends(get_oauth_callback_db)]
