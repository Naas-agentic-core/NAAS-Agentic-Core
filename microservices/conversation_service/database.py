import os

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

CONV_DATABASE_URL = os.environ.get("CONV_DATABASE_URL", "sqlite+aiosqlite:///:memory:")

engine = create_async_engine(CONV_DATABASE_URL, echo=False)

AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_conv_db_session():
    async with AsyncSessionLocal() as session:
        yield session
