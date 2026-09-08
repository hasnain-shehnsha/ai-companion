import asyncio
from app.core.database import engine, Base
from app.models.user import User
from app.models.subscription import DailySubscription

async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        print("Tables created successfully.")

asyncio.run(create_tables())
