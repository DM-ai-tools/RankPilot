"""Async SQLAlchemy engine — configured from app lifespan."""

from sqlalchemy.engine.url import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

_engine: AsyncEngine | None = None
_session_maker: async_sessionmaker[AsyncSession] | None = None


def _asyncpg_connect_args(database_url: str) -> dict:
    """Railway public Postgres proxies (*.railway.app) expect TLS; private *.railway.internal usually does not."""
    try:
        u = make_url(database_url)
    except Exception:
        return {}
    host = (u.host or "").lower()
    q = {k.lower(): v for k, v in (u.query or {}).items()}
    sslmode = (q.get("sslmode") or "").lower()
    if sslmode in ("require", "verify-ca", "verify-full"):
        return {"ssl": True}
    if (q.get("ssl") or "").lower() in ("true", "t", "1"):
        return {"ssl": True}
    if host.endswith(".railway.app") and ".railway.internal" not in host:
        return {"ssl": True}
    return {}


def configure_engine(database_url: str, *, echo: bool = False) -> None:
    global _engine, _session_maker
    if _engine is not None:
        return
    extra = _asyncpg_connect_args(database_url)
    _engine = create_async_engine(
        database_url,
        echo=echo,
        pool_pre_ping=True,
        connect_args=extra,
    )
    _session_maker = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)


async def dispose_engine() -> None:
    global _engine, _session_maker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_maker = None


def session_maker() -> async_sessionmaker[AsyncSession]:
    if _session_maker is None:
        raise RuntimeError("Database not configured — call configure_engine in lifespan")
    return _session_maker

