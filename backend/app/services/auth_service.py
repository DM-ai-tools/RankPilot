"""Issue JWT after verifying credentials (server-side only)."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException, status
from jose import jwt
from passlib.context import CryptContext
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.schemas.auth_login import LoginRequest, LoginResponse

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthService:
    def __init__(self, settings: Settings):
        self._settings = settings

    async def login(self, session: AsyncSession, body: LoginRequest) -> LoginResponse:
        try:
            result = await session.execute(
                text(
                    """
                    SELECT client_id, password_hash
                    FROM rp_clients
                    WHERE login_username IS NOT NULL
                      AND lower(login_username::text) = lower(:username)
                    LIMIT 1
                    """
                ),
                {"username": body.username},
            )
        except ProgrammingError as e:
            msg = str(e.orig) if getattr(e, "orig", None) else str(e)
            if "rp_clients" in msg and "does not exist" in msg:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=(
                        "RankPilot schema is missing on this database. "
                        "From the backend folder run: python scripts/apply_migrations.py "
                        "(needs psql). Or apply infra/sql 001→007 manually."
                    ),
                ) from e
            raise
        row = result.mappings().first()
        if not row or not row["password_hash"]:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password",
            )
        if not _pwd.verify(body.password, str(row["password_hash"])):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password",
            )

        client_id: UUID = row["client_id"]
        now = datetime.now(UTC)
        exp = now + timedelta(minutes=self._settings.access_token_expire_minutes)
        payload = {
            "client_id": str(client_id),
            "sub": str(client_id),
            "iat": int(now.timestamp()),
            "exp": int(exp.timestamp()),
        }
        token = jwt.encode(
            payload, self._settings.jwt_secret_key, algorithm=self._settings.jwt_algorithm
        )
        return LoginResponse(
            access_token=token,
            expires_in=self._settings.access_token_expire_minutes * 60,
        )