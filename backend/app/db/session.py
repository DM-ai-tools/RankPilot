"""Async SQLAlchemy engine — configured from app lifespan."""

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

_engine: AsyncEngine | None = None
_session_maker: async_sessionmaker[AsyncSession] | None = None


def configure_engine(database_url: str, *, echo: bool = False) -> None:
    global _engine, _session_maker
    if _engine is not None:
        return
    _engine = create_async_engine(database_url, echo=echo, pool_pre_ping=True)
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

