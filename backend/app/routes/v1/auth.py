"""Password login — returns JWT (minted on server). No Bearer required."""

from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.deps import LoginDbSession
from app.schemas.auth_login import LoginRequest, LoginResponse
from app.services.auth_service import AuthService

router = APIRouter()


def get_auth_service(settings: Settings = Depends(get_settings)) -> AuthService:
    return AuthService(settings)


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    session: LoginDbSession,
    svc: AuthService = Depends(get_auth_service),
) -> LoginResponse:
    return await svc.login(session, body)
