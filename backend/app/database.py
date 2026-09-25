import logging
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

db_url = settings.database_url
is_sqlite = "sqlite" in db_url

connect_args = {"check_same_thread": False} if is_sqlite else {}
engine_kwargs = {"echo": settings.debug}
if not is_sqlite:
    engine_kwargs["pool_pre_ping"] = True

engine = create_async_engine(db_url, connect_args=connect_args, **engine_kwargs)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
