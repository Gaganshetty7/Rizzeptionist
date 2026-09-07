import asyncio

from sqlalchemy import text

from config import DATABASE_URL
from db import create_engine, create_session_factory


async def main():
    engine = create_engine(DATABASE_URL)
    session_factory = create_session_factory(engine)

    async with session_factory() as session:
        result = await session.execute(text("SELECT 1"))
        print("Result:", result.scalar())

    await engine.dispose()
    print("Database connection closed")


asyncio.run(main())