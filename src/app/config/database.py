from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config.settings import settings

client: AsyncIOMotorClient = AsyncIOMotorClient(settings.MONGODB_URL)
db: AsyncIOMotorDatabase = client[settings.DATABASE_NAME]
