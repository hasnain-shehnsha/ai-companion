import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import AsyncSessionLocal
from app.api.endpoints.whatsapp import process_message

async def main():
    async with AsyncSessionLocal() as db:
        await process_message(db, "923404386378", "Hello")

asyncio.run(main())
