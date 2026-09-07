from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker 
from sqlalchemy.ext.asyncio.engine import create_async_engine, AsyncEngine

def create_engine(database_url: str) -> AsyncEngine:
    url = make_url(database_url)

    query = dict(url.query)
    query.pop("sslmode", None)
    query.pop("channel_binding", None)

    url = url.set(
        drivername="postgresql+asyncpg",
        query=query,
    )

    return create_async_engine(
        url,
        connect_args={"ssl": "require"},
        pool_pre_ping=True,
    )

def create_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False
    )