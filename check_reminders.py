import asyncio
from sqlalchemy.future import select
from app.core.database import AsyncSessionLocal
from app.models.reminder import Reminder

async def main():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Reminder))
        reminders = result.scalars().all()
        for r in reminders:
            print(f"ID: {r.id}, UserID: {r.user_id}, Message: '{r.message}', Status: {r.status}, RemindAt: {r.remind_at}")

asyncio.run(main())
