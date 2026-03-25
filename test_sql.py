import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def main():
    try:
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.connect() as conn:
            # sqlite doesn't support SET search_path but we can just syntax check.
            pass
    except Exception as e:
        print(e)

if __name__ == "__main__":
    asyncio.run(main())
