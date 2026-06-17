"""
Application lifespan manager.

Handles:
  - MongoDB connection init (Beanie ODM)
  - Redis ping on startup
  - Background workers (momentum recalculation, recurring action generation)
  - Redis pub/sub subscriber task
"""

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import beanie
from fastapi import FastAPI
from loguru import logger
from motor.motor_asyncio import AsyncIOMotorClient

from app.config.settings import settings
from app.core.logging import setup_logging
from app.events.subscribers import start_subscriber


async def _init_db() -> None:
    """Initialise Beanie ODM with all document models."""
    # Models imported here to avoid circular imports at module level
    from app.models.goal import Goal
    from app.models.action import Action
    from app.models.phase import Phase

    mongo_client = AsyncIOMotorClient(settings.MONGODB_URL)
    await beanie.init_beanie(
        database=mongo_client[settings.DATABASE_NAME],
        document_models=[Goal, Phase, Action],
    )
    logger.info(f"MongoDB connected → database: {settings.DATABASE_NAME}")


async def _ping_redis() -> None:
    from app.config.redis import redis_client

    await redis_client.ping()
    logger.info("Redis connected ✓")


async def _start_workers() -> None:
    from app.workers.momentum_worker import run_momentum_recalc
    from app.workers.recurring_action_worker import run_recurring_action_gen

    asyncio.create_task(run_momentum_recalc(), name="momentum_recalc")
    asyncio.create_task(run_recurring_action_gen(), name="recurring_action_gen")
    logger.info("Background workers started ✓")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    setup_logging()
    logger.info(f"Starting {settings.APP_NAME} [{settings.ENVIRONMENT}]")

    await _init_db()
    await _ping_redis()

    # Start event subscriber
    subscriber_task = asyncio.create_task(start_subscriber(), name="event_subscriber")

    # Start background workers
    await _start_workers()

    yield  # ── App is running ─────────────────────────────────────

    logger.info("Shutting down — cancelling background tasks...")
    subscriber_task.cancel()
    try:
        await subscriber_task
    except asyncio.CancelledError:
        pass
    logger.info(f"{settings.APP_NAME} shut down cleanly.")
