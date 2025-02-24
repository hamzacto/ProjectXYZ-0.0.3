import asyncio
from sqlmodel import text
from sqlalchemy.ext.asyncio import AsyncSession
from contextlib import asynccontextmanager

@asynccontextmanager
async def get_session():
    from sqlmodel import create_engine
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    
    # Get your database URL from environment or config
    DATABASE_URL = "sqlite+aiosqlite:///langflow.db"  # adjust as needed
    engine = create_async_engine(DATABASE_URL)
    async with AsyncSession(engine) as session:
        yield session

async def drop_alembic():
    async with get_session() as session:
        try:
            await session.execute(text("DROP TABLE IF EXISTS alembic_version"))
            await session.commit()
        except Exception as exc:
            await session.rollback()
            raise exc

def run_drop_alembic():
    asyncio.run(drop_alembic())

if __name__ == "__main__":
    run_drop_alembic() 